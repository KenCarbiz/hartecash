"""AI voice agent — the wedge.

VAN's "automated outreach" is templated SMS. Toma + Mia.inc do voice
for service-side. Nobody owns the FSBO acquisition voice slot. This
module is the minimum viable demo path.

Flow:

  POST /voice/calls (auth)            -> initiate outbound call
  POST /voice/twiml/start/{call_id}   -> Twilio fetches when call answered
  POST /voice/twiml/turn/{call_id}    -> Twilio posts seller's speech
  POST /voice/twiml/status/{call_id}  -> Twilio posts call-completed
                                          callback; we run the
                                          structured-intake extractor

The TwiML endpoints are PUBLIC (Twilio calls them server-to-server),
guarded by HMAC signature validation against TWILIO_AUTH_TOKEN.

The conversational AI is pragmatic: each turn we feed the recent
transcript history to Claude with a system prompt that prescribes the
agent's personality + the data we want to collect. Output is either
the next thing to say + a hint to keep listening, OR a hangup signal
once we've covered the high-priority fields. A real production agent
would use OpenAI Realtime or Twilio ConversationRelay; this turn-by-
turn pattern is good enough to demo and ships today.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.config import settings
from fsbo.db import get_session
from fsbo.messaging.tcpa import check_send_allowed
from fsbo.messaging.twilio_signature import verify_twilio_signature
from fsbo.models import Lead, Listing, VoiceCall
from fsbo.voice.intake import extract_from_turns, merge_intake

router = APIRouter(tags=["voice"])


class StartCallIn(BaseModel):
    lead_id: int
    to_number: str | None = None  # override the listing's seller_phone


class StartCallOut(BaseModel):
    call_id: int
    twilio_call_sid: str | None
    status: str


# -- Outbound initiation ------------------------------------------------


@router.post("/voice/calls", response_model=StartCallOut, status_code=201)
def start_call(
    payload: StartCallIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    request: Request,
) -> StartCallOut:
    """Kick off an outbound voice call.

    Same permission shape as /messages/send: dealer must own the lead,
    TCPA gate must allow, listing must have a phone (or override).
    """
    lead = db.get(Lead, payload.lead_id)
    if not lead or lead.dealer_id != dealer_id:
        raise HTTPException(404, "lead not found")
    listing = db.get(Listing, lead.listing_id)
    to = payload.to_number
    if not to:
        to = listing.seller_phone if listing else None
    if not to:
        raise HTTPException(400, "no destination number on lead's listing")

    # TCPA gate (same as SMS — same federal rules apply to robocalls)
    listing_zip = listing.zip_code if listing else None
    gate = check_send_allowed(
        db, dealer_id=dealer_id, phone=to, zip_code=listing_zip
    )
    if not gate.allowed:
        raise HTTPException(
            status_code=451,
            detail=f"voice blocked: {gate.blocked_reason} — {gate.detail}",
        )

    # Pre-create the VoiceCall row so the TwiML callbacks can find it
    # by id even if the Twilio call_sid races us.
    call = VoiceCall(
        lead_id=lead.id,
        dealer_id=dealer_id,
        to_number=to,
        from_number=settings.twilio_from_number or None,
        status="queued",
    )
    db.add(call)
    db.flush()

    # In dev / when Twilio isn't configured, return the row in 'simulated'
    # state so the dashboard demo path works without billing.
    if not (
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_from_number
    ):
        call.status = "simulated"
        return StartCallOut(
            call_id=call.id,
            twilio_call_sid=None,
            status="simulated",
        )

    # Real Twilio dial. Lazy import so the module loads without the
    # twilio SDK in dev.
    try:
        from twilio.rest import Client  # type: ignore
    except ImportError:
        raise HTTPException(
            500, "twilio python SDK not installed; run `uv add twilio`"
        )

    base = (settings.app_origin or "").rstrip("/") or _request_origin(request)
    twiml_start = f"{base}/voice/twiml/start/{call.id}"
    status_callback = f"{base}/voice/twiml/status/{call.id}"

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    try:
        twcall = client.calls.create(
            to=to,
            from_=settings.twilio_from_number,
            url=twiml_start,
            method="POST",
            status_callback=status_callback,
            status_callback_method="POST",
            status_callback_event=["completed"],
        )
    except Exception as e:  # noqa: BLE001 - bubble Twilio errors
        call.status = f"failed:{str(e)[:32]}"
        raise HTTPException(502, f"twilio call create failed: {e}") from e

    call.twilio_call_sid = twcall.sid
    call.status = twcall.status or "queued"
    return StartCallOut(
        call_id=call.id, twilio_call_sid=twcall.sid, status=call.status
    )


def _request_origin(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.netloc
    return f"{proto}://{host}"


# -- TwiML endpoints (Twilio -> us, signature-verified) -----------------


def _twiml(xml: str) -> Response:
    return Response(content=xml, media_type="application/xml")


def _opening_line(listing: Listing | None) -> str:
    """Friendly + identifies the dealer + sets expectation. Refined
    over time; today it's a clear safe default."""
    bits = ["Hi! I'm calling about your"]
    if listing:
        if listing.year:
            bits.append(str(listing.year))
        if listing.make:
            bits.append(listing.make)
        if listing.model:
            bits.append(listing.model)
    bits.append(
        "you have for sale online. I'm an AI assistant for a "
        "local dealership. Is the vehicle still available?"
    )
    return " ".join(bits)


@router.post("/voice/twiml/start/{call_id}")
async def twiml_start(
    call_id: int,
    db: Annotated[Session, Depends(get_session)],
    _verified: Annotated[None, Depends(verify_twilio_signature)],
) -> Response:
    """Twilio fetches this URL when the call connects. Returns TwiML
    that says the opening line then waits for the seller's reply."""
    call = db.get(VoiceCall, call_id)
    if not call:
        return _twiml('<Response><Hangup/></Response>')

    listing = None
    lead = db.get(Lead, call.lead_id)
    if lead:
        listing = db.get(Listing, lead.listing_id)

    line = _opening_line(listing)
    call.turns = list(call.turns or []) + [
        {"role": "ai", "text": line, "at": _now_iso()}
    ]
    call.status = "in_progress"
    db.flush()

    next_turn = f"/voice/twiml/turn/{call_id}"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna">{_xml_escape(line)}</Say>
  <Gather input="speech" timeout="5" speechTimeout="auto"
          action="{next_turn}" method="POST">
    <Say voice="Polly.Joanna">Go ahead.</Say>
  </Gather>
  <Redirect>{next_turn}</Redirect>
</Response>"""
    return _twiml(xml)


# Hard cap so a runaway loop of "huh?" / "what?" doesn't run up bills.
MAX_TURNS = 14


@router.post("/voice/twiml/turn/{call_id}")
async def twiml_turn(
    call_id: int,
    db: Annotated[Session, Depends(get_session)],
    request: Request,
    _verified: Annotated[None, Depends(verify_twilio_signature)],
    SpeechResult: Annotated[str | None, Form()] = None,
    Confidence: Annotated[str | None, Form()] = None,
) -> Response:
    call = db.get(VoiceCall, call_id)
    if not call:
        return _twiml('<Response><Hangup/></Response>')

    seller_text = (SpeechResult or "").strip()
    turns = list(call.turns or [])
    if seller_text:
        turns.append(
            {"role": "seller", "text": seller_text, "at": _now_iso()}
        )

    # Decide what to say next. Cheap path: if we have enough info OR we
    # hit the cap, wrap the call. Otherwise prompt for the next missing
    # field.
    if len(turns) >= MAX_TURNS or _has_enough(turns):
        line = (
            "Got it, thanks for the info. "
            "We'll be in touch shortly with a firm offer. Have a good one!"
        )
        turns.append({"role": "ai", "text": line, "at": _now_iso()})
        call.turns = turns
        call.status = "wrapping"
        db.flush()
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna">{_xml_escape(line)}</Say>
  <Hangup/>
</Response>"""
        return _twiml(xml)

    # Next prompt is templated (no LLM call per turn — keep it cheap +
    # latency-friendly). The intake extractor runs once at end-of-call.
    line = _next_prompt(turns)
    turns.append({"role": "ai", "text": line, "at": _now_iso()})
    call.turns = turns
    db.flush()

    next_turn = f"/voice/twiml/turn/{call_id}"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna">{_xml_escape(line)}</Say>
  <Gather input="speech" timeout="5" speechTimeout="auto"
          action="{next_turn}" method="POST"/>
  <Redirect>{next_turn}</Redirect>
</Response>"""
    return _twiml(xml)


# Field-acquisition order — we walk this list, asking for each field
# we don't have evidence of yet. Naive keyword matching against the
# seller's prior turns; the real extractor at end-of-call does the
# proper structured pull.
_PROMPT_LADDER = [
    ("price", "And what's the lowest you'd take in cash?"),
    ("mileage", "About how many miles is the vehicle showing?"),
    ("title", "Do you have the title in hand, or is there a lien on it?"),
    ("drives", "Does it run and drive without any issues?"),
    ("damage", "Any accidents or body damage I should know about?"),
    ("when", "When would be a good time for one of our buyers to come look at it?"),
]


def _next_prompt(turns: list[dict]) -> str:
    seller_text = " ".join(
        t.get("text", "") for t in turns if t.get("role") == "seller"
    ).lower()
    for key, line in _PROMPT_LADDER:
        if key == "price" and ("$" in seller_text or "thousand" in seller_text or "dollar" in seller_text):
            continue
        if key == "mileage" and ("mile" in seller_text or "k on" in seller_text):
            continue
        if key == "title" and ("title" in seller_text or "lien" in seller_text):
            continue
        if key == "drives" and (
            "drive" in seller_text or "runs" in seller_text or "running" in seller_text
        ):
            continue
        if key == "damage" and (
            "accident" in seller_text or "damage" in seller_text or "wreck" in seller_text or "clean" in seller_text
        ):
            continue
        if key == "when" and (
            "today" in seller_text or "tomorrow" in seller_text or
            "morning" in seller_text or "afternoon" in seller_text or
            "weekend" in seller_text
        ):
            continue
        return line
    return "Anything else I should know about the vehicle?"


def _has_enough(turns: list[dict]) -> bool:
    """Coarse "we covered the must-haves" check — price + mileage +
    title + something about condition."""
    seller_text = " ".join(
        t.get("text", "") for t in turns if t.get("role") == "seller"
    ).lower()
    has_price = "$" in seller_text or "thousand" in seller_text or "dollar" in seller_text
    has_miles = "mile" in seller_text or "k on" in seller_text
    has_title = "title" in seller_text or "lien" in seller_text
    has_condition = (
        "drive" in seller_text or "runs" in seller_text or "clean" in seller_text
    )
    return sum([has_price, has_miles, has_title, has_condition]) >= 3


@router.post("/voice/twiml/status/{call_id}")
async def twiml_status(
    call_id: int,
    db: Annotated[Session, Depends(get_session)],
    _verified: Annotated[None, Depends(verify_twilio_signature)],
    CallStatus: Annotated[str, Form()] = "unknown",
    CallDuration: Annotated[str | None, Form()] = None,
) -> dict[str, str]:
    """Twilio fires this when the call ends. We finalize state +
    extract the structured intake JSON via Claude."""
    call = db.get(VoiceCall, call_id)
    if not call:
        return {"ok": "1", "matched": "none"}

    call.status = CallStatus
    if CallDuration:
        try:
            call.duration_seconds = int(CallDuration)
        except ValueError:
            pass
    call.updated_at = datetime.now(timezone.utc)

    # Run the structured-output extractor over the full transcript and
    # write back to BOTH the VoiceCall.intake (per-call) and the
    # Lead.seller_intake (aggregated across all calls).
    intake = extract_from_turns(list(call.turns or []))
    call.intake = intake.as_dict()

    lead = db.get(Lead, call.lead_id)
    if lead:
        lead.seller_intake = merge_intake(lead.seller_intake or {}, intake)
        lead.updated_at = datetime.now(timezone.utc)

    db.flush()

    # Webhook fan-out: notify any DMS / CRM the dealer subscribed to
    # voice_call.completed. Best-effort — never let a webhook failure
    # break Twilio's status callback.
    if CallStatus == "completed":
        from fsbo.webhooks.delivery import enqueue_for_voice_call_completed

        try:
            enqueue_for_voice_call_completed(db, call)
        except Exception:  # noqa: BLE001
            pass

    return {"ok": "1", "call_id": str(call.id)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# -- Read endpoint for the dashboard ------------------------------------


class VoiceCallOut(BaseModel):
    id: int
    lead_id: int
    status: str
    to_number: str
    duration_seconds: int | None
    turns: list
    intake: dict
    created_at: datetime


@router.get("/voice/calls/{call_id}", response_model=VoiceCallOut)
def get_call(
    call_id: int,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> VoiceCallOut:
    call = db.get(VoiceCall, call_id)
    if not call or call.dealer_id != dealer_id:
        raise HTTPException(404, "call not found")
    return VoiceCallOut(
        id=call.id,
        lead_id=call.lead_id,
        status=call.status,
        to_number=call.to_number,
        duration_seconds=call.duration_seconds,
        turns=list(call.turns or []),
        intake=dict(call.intake or {}),
        created_at=call.created_at,
    )


@router.get("/leads/{lead_id}/voice-calls", response_model=list[VoiceCallOut])
def list_calls_for_lead(
    lead_id: int,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> list[VoiceCallOut]:
    lead = db.get(Lead, lead_id)
    if not lead or lead.dealer_id != dealer_id:
        raise HTTPException(404, "lead not found")
    rows = db.scalars(
        select(VoiceCall)
        .where(VoiceCall.lead_id == lead_id)
        .order_by(VoiceCall.created_at.desc())
    ).all()
    return [
        VoiceCallOut(
            id=c.id,
            lead_id=c.lead_id,
            status=c.status,
            to_number=c.to_number,
            duration_seconds=c.duration_seconds,
            turns=list(c.turns or []),
            intake=dict(c.intake or {}),
            created_at=c.created_at,
        )
        for c in rows
    ]
