"""SMS + email send + Twilio + SendGrid Inbound Parse webhook endpoints."""

import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.config import settings
from fsbo.config import settings as app_settings
from fsbo.db import get_session
from fsbo.messaging.email_client import send_email
from fsbo.messaging.intent import classify_inbound
from fsbo.messaging.tcpa import (
    check_send_allowed,
    is_stop_keyword,
    record_opt_out,
)
from fsbo.messaging.twilio_client import send_sms
from fsbo.messaging.twilio_signature import verify_twilio_signature
from fsbo.models import Interaction, InteractionKind, Lead, Listing, Message

router = APIRouter(tags=["messaging"])


class SendSmsIn(BaseModel):
    lead_id: int
    body: str
    to_number: str | None = None  # override the listing's seller_phone if provided


class SendSmsOut(BaseModel):
    message_id: int
    twilio_sid: str | None
    status: str
    error: str | None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dealer_id: str
    lead_id: int | None
    direction: str
    channel: str = "sms"
    from_number: str | None = None
    to_number: str | None = None
    from_email: str | None = None
    to_email: str | None = None
    subject: str | None = None
    body: str
    status: str
    twilio_sid: str | None = None
    created_at: datetime
    delivered_at: datetime | None


@router.post("/messages/send", response_model=SendSmsOut)
async def send(
    payload: SendSmsIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> SendSmsOut:
    lead = db.get(Lead, payload.lead_id)
    if not lead or lead.dealer_id != dealer_id:
        raise HTTPException(404, "lead not found")

    listing = db.get(Listing, lead.listing_id)
    to = payload.to_number
    if not to:
        to = listing.seller_phone if listing else None
    if not to:
        raise HTTPException(400, "no destination number on lead's listing")

    # TCPA gate: block sends that violate quiet hours, opt-outs, or
    # (when strict-consent mode is enabled) lack a consent record. We
    # log a refused-send Interaction so the audit trail captures the
    # block. Returning 451 (Unavailable for Legal Reasons) lets the
    # dashboard surface the reason without a generic 4xx.
    listing_zip = listing.zip_code if listing else None
    gate = check_send_allowed(
        db, dealer_id=dealer_id, phone=to, zip_code=listing_zip
    )
    if not gate.allowed:
        db.add(
            Interaction(
                lead_id=lead.id,
                kind=InteractionKind.NOTE.value,
                body=f"sms blocked: {gate.blocked_reason} ({gate.detail})",
                actor=dealer_id,
            )
        )
        raise HTTPException(
            status_code=451,
            detail=f"sms blocked: {gate.blocked_reason} — {gate.detail}",
        )

    result = await send_sms(to_number=to, body=payload.body)

    msg = Message(
        dealer_id=dealer_id,
        lead_id=lead.id,
        direction="outbound",
        to_number=to,
        body=payload.body,
        status=result.status,
        twilio_sid=result.sid,
        error_code=result.error_code,
    )
    db.add(msg)
    db.add(
        Interaction(
            lead_id=lead.id,
            kind=InteractionKind.TEXT.value,
            direction="outbound",
            body=payload.body,
        )
    )
    lead.updated_at = datetime.now(timezone.utc)
    db.flush()

    return SendSmsOut(
        message_id=msg.id,
        twilio_sid=result.sid,
        status=result.status,
        error=result.error_message,
    )


# ---- Email outreach -------------------------------------------------


class SendEmailIn(BaseModel):
    lead_id: int
    subject: str
    body: str
    to_email: str | None = None  # override listing.seller_email if provided


class SendEmailOut(BaseModel):
    message_id: int
    backend: str
    sent: bool
    error: str | None


@router.post("/messages/email/send", response_model=SendEmailOut)
async def send_email_to_seller(
    payload: SendEmailIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> SendEmailOut:
    """Send an email to the lead's seller via the configured email
    backend (SendGrid / SMTP / console). Email is governed by CAN-SPAM
    + state spam laws — we don't enforce a quiet-hours window because
    email isn't time-sensitive in the same way SMS is, but we DO
    honor the SMS opt-out registry: if the seller texted STOP, we
    refuse to email them too. Aggressive on purpose.
    """
    lead = db.get(Lead, payload.lead_id)
    if not lead or lead.dealer_id != dealer_id:
        raise HTTPException(404, "lead not found")

    listing = db.get(Listing, lead.listing_id)
    to = (payload.to_email or "").strip()
    if not to and listing:
        to = (listing.seller_email or "").strip()
    if not to or "@" not in to:
        raise HTTPException(
            400, "no destination email on lead's listing"
        )

    # Honor the SMS opt-out registry as a "do not contact" signal even
    # for email. A seller who said STOP doesn't want to hear from us
    # on any channel.
    if listing and listing.seller_phone:
        gate = check_send_allowed(
            db,
            dealer_id=dealer_id,
            phone=listing.seller_phone,
            zip_code=listing.zip_code,
        )
        if gate.blocked_reason == "opted_out":
            db.add(
                Interaction(
                    lead_id=lead.id,
                    kind=InteractionKind.NOTE.value,
                    body=f"email blocked: opted_out (carries over from SMS)",
                    actor=dealer_id,
                )
            )
            raise HTTPException(
                status_code=451,
                detail="email blocked: opted_out — seller previously sent STOP",
            )

    result = await send_email(
        to=to,
        subject=payload.subject,
        text_body=payload.body,
        from_address=app_settings.email_from or None,
    )

    msg = Message(
        dealer_id=dealer_id,
        lead_id=lead.id,
        direction="outbound",
        channel="email",
        from_email=app_settings.email_from or None,
        to_email=to,
        subject=payload.subject[:256],
        body=payload.body,
        status="sent" if result.sent else "failed",
        error_code=result.error[:32] if result.error else None,
    )
    db.add(msg)
    db.add(
        Interaction(
            lead_id=lead.id,
            kind=InteractionKind.EMAIL.value,
            direction="outbound",
            body=payload.body,
        )
    )
    lead.updated_at = datetime.now(timezone.utc)
    db.flush()

    return SendEmailOut(
        message_id=msg.id,
        backend=result.backend,
        sent=result.sent,
        error=result.error,
    )


@router.get("/leads/{lead_id}/messages", response_model=list[MessageOut])
def list_messages(
    lead_id: int,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> list[MessageOut]:
    lead = db.get(Lead, lead_id)
    if not lead or lead.dealer_id != dealer_id:
        raise HTTPException(404, "lead not found")
    rows = db.scalars(
        select(Message)
        .where(Message.lead_id == lead_id)
        .order_by(Message.created_at.desc())
    ).all()
    return [MessageOut.model_validate(r) for r in rows]


# ---- Twilio webhooks ----
# Twilio POSTs x-www-form-urlencoded status updates and inbound MMS/SMS
# to the URL you configure in the console. Guarded by HMAC validation
# of X-Twilio-Signature against TWILIO_AUTH_TOKEN. The signature dep
# fetches the form via request.form() and caches it on request.state
# so the route's Form() params can read the same body.


@router.post(
    "/webhooks/twilio/status",
    dependencies=[Depends(verify_twilio_signature)],
)
async def twilio_status(
    db: Annotated[Session, Depends(get_session)],
    MessageSid: Annotated[str, Form()],
    MessageStatus: Annotated[str, Form()],
    ErrorCode: Annotated[str | None, Form()] = None,
) -> dict[str, str]:
    # Match the Twilio SID back to our Message row and update status.
    msg = db.scalar(select(Message).where(Message.twilio_sid == MessageSid))
    if msg:
        msg.status = MessageStatus
        if ErrorCode:
            msg.error_code = ErrorCode
        if MessageStatus == "delivered":
            msg.delivered_at = datetime.now(timezone.utc)
        db.flush()
        return {"ok": "1", "matched": str(msg.id)}
    return {"ok": "1", "matched": "none"}


@router.post(
    "/webhooks/twilio/inbound",
    dependencies=[Depends(verify_twilio_signature)],
)
async def twilio_inbound(
    db: Annotated[Session, Depends(get_session)],
    From: Annotated[str, Form()],
    To: Annotated[str, Form()],
    Body: Annotated[str, Form()],
    MessageSid: Annotated[str, Form()],
) -> str:
    # Route the inbound message to whichever lead has a matching seller_phone.
    # Multi-dealer matching is best-effort: we pick the most recent lead.
    clean = _digits(From)
    lead = None
    for candidate_lead in db.scalars(
        select(Lead).order_by(Lead.updated_at.desc())
    ).all():
        listing = db.get(Listing, candidate_lead.listing_id)
        if listing and _digits(listing.seller_phone) == clean:
            lead = candidate_lead
            break

    if lead:
        db.add(
            Message(
                dealer_id=lead.dealer_id,
                lead_id=lead.id,
                direction="inbound",
                from_number=From,
                to_number=To,
                body=Body,
                status="received",
                twilio_sid=MessageSid,
            )
        )
        # TCPA: STOP / END / QUIT / UNSUBSCRIBE → immediate opt-out.
        # Per CTIA we have to honor within 24 hours; we honor instantly
        # and log a status_change interaction with the verbatim text.
        if is_stop_keyword(Body):
            record_opt_out(
                db,
                dealer_id=lead.dealer_id,
                phone=From,
                source="stop_keyword",
                note=(Body or "")[:128],
            )
            db.add(
                Interaction(
                    lead_id=lead.id,
                    kind=InteractionKind.STATUS_CHANGE.value,
                    body=f"opted out via STOP keyword: {(Body or '').strip()[:80]}",
                    actor="system",
                )
            )
        db.add(
            Interaction(
                lead_id=lead.id,
                kind=InteractionKind.TEXT.value,
                direction="inbound",
                body=Body,
            )
        )
        lead.updated_at = datetime.now(timezone.utc)

        # VAN-parity: when the seller tells us the car is sold or no
        # longer available, auto-mark the listing + close the lead so
        # we stop chasing it. Don't auto-close on "negative" (could be
        # a wrong number we can correct) or "interested" (obvious).
        intent = classify_inbound(Body)
        if intent.intent == "sold":
            listing = db.get(Listing, lead.listing_id)
            if listing and listing.sold_at is None:
                listing.sold_at = datetime.now(timezone.utc)
                listing.sold_signal = (Body or "")[:256]
                listing.auto_hidden = True
                listing.auto_hide_reason = (
                    listing.auto_hide_reason or "seller confirmed sold via SMS"
                )
                db.flush()
            if lead.status not in ("purchased", "lost"):
                lead.status = "lost"
                db.add(
                    Interaction(
                        lead_id=lead.id,
                        kind=InteractionKind.STATUS_CHANGE.value,
                        body=f"auto-closed: seller confirmed sold ({(Body or '').strip()[:80]})",
                        actor="system",
                    )
                )
        elif intent.intent == "not_for_sale":
            if lead.status not in ("purchased", "lost"):
                lead.status = "lost"
                db.add(
                    Interaction(
                        lead_id=lead.id,
                        kind=InteractionKind.STATUS_CHANGE.value,
                        body=f"auto-closed: seller withdrew listing ({(Body or '').strip()[:80]})",
                        actor="system",
                    )
                )

    # Return empty TwiML so Twilio doesn't auto-reply.
    return "<Response></Response>"


def _digits(phone: str | None) -> str:
    if not phone:
        return ""
    return "".join(c for c in phone if c.isdigit())[-10:]


def _email_only(addr: str | None) -> str:
    """Strip a 'Name <name@host>' header to just the email part."""
    if not addr:
        return ""
    s = addr.strip()
    if "<" in s and ">" in s:
        s = s[s.find("<") + 1 : s.find(">")]
    return s.strip().lower()


# ---- Inbound email (SendGrid Inbound Parse webhook) -----------------
#
# Configure SendGrid: https://app.sendgrid.com → Settings →
# Inbound Parse → add hostname (mx record on inbound.autoacquisition.io
# pointing at SendGrid) → POST URL
# https://api.autoacquisition.io/webhooks/email/inbound
#
# SendGrid posts multipart/form-data with from/to/subject/text/html.
# We don't validate signatures here — Inbound Parse doesn't sign;
# protection is via shared-secret query param (FSBO_INBOUND_EMAIL_TOKEN
# env). Misconfigured deploys silently accept everything in dev/CI.


@router.post("/webhooks/email/inbound")
async def inbound_email(
    db: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, str]:
    """SendGrid Inbound Parse target. Routes the email to whichever
    Lead has a matching seller_email + logs a Message + Interaction
    + runs the same intent classifier we use for inbound SMS so a
    "we already sold it" email auto-closes the lead."""
    # Optional shared-secret on the URL: ?token=...
    expected_token = settings.inbound_email_token
    if expected_token:
        token = request.query_params.get("token")
        if token != expected_token:
            raise HTTPException(403, "invalid inbound email token")

    form = await request.form()
    from_addr = _email_only(str(form.get("from") or ""))
    to_addr = _email_only(str(form.get("to") or ""))
    subject = (str(form.get("subject") or "")).strip()[:256]
    # SendGrid sends the plain-text body as 'text', the HTML version as
    # 'html'. Prefer text; fall back to html with tags stripped (cheap).
    body_text = (str(form.get("text") or "")).strip()
    if not body_text:
        body_html = str(form.get("html") or "")
        # Cheap tag strip — for our intent classifier purposes this is fine.
        body_text = re.sub(r"<[^>]+>", " ", body_html)
        body_text = re.sub(r"\s+", " ", body_text).strip()

    if not from_addr:
        return {"ok": "1", "matched": "no_from"}

    # Route to a Lead via Listing.seller_email. Pick the most-recently-
    # updated lead pointing at a listing with this email — handles the
    # case where multiple dealers chase the same seller.
    lead = None
    rows = db.scalars(
        select(Lead)
        .join(Listing, Listing.id == Lead.listing_id)
        .where(Listing.seller_email == from_addr)
        .order_by(Lead.updated_at.desc())
    ).all()
    if rows:
        lead = rows[0]

    if not lead:
        return {"ok": "1", "matched": "none", "from": from_addr}

    db.add(
        Message(
            dealer_id=lead.dealer_id,
            lead_id=lead.id,
            direction="inbound",
            channel="email",
            from_email=from_addr,
            to_email=to_addr or None,
            subject=subject or None,
            body=body_text or "(empty body)",
            status="received",
        )
    )
    db.add(
        Interaction(
            lead_id=lead.id,
            kind=InteractionKind.EMAIL.value,
            direction="inbound",
            body=(f"[{subject}] " if subject else "") + body_text,
        )
    )
    lead.updated_at = datetime.now(timezone.utc)

    # Same intent ladder as inbound SMS — auto-close on sold /
    # not_for_sale signals so dealers stop chasing dead leads.
    intent = classify_inbound(body_text)
    if intent.intent == "sold":
        listing = db.get(Listing, lead.listing_id)
        if listing and listing.sold_at is None:
            listing.sold_at = datetime.now(timezone.utc)
            listing.sold_signal = body_text[:256]
            listing.auto_hidden = True
            listing.auto_hide_reason = (
                listing.auto_hide_reason
                or "seller confirmed sold via email"
            )
            db.flush()
        if lead.status not in ("purchased", "lost"):
            lead.status = "lost"
            db.add(
                Interaction(
                    lead_id=lead.id,
                    kind=InteractionKind.STATUS_CHANGE.value,
                    body=f"auto-closed: seller confirmed sold via email ({body_text[:80]})",
                    actor="system",
                )
            )
    elif intent.intent == "not_for_sale":
        if lead.status not in ("purchased", "lost"):
            lead.status = "lost"
            db.add(
                Interaction(
                    lead_id=lead.id,
                    kind=InteractionKind.STATUS_CHANGE.value,
                    body=f"auto-closed: seller withdrew via email ({body_text[:80]})",
                    actor="system",
                )
            )

    db.flush()
    return {"ok": "1", "matched": str(lead.id)}
