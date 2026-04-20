"""SMS send + Twilio webhook endpoints."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.db import get_session
from fsbo.messaging.twilio_client import send_sms
from fsbo.models import Interaction, InteractionKind, Lead, Listing, Message

router = APIRouter(tags=["messaging"])

DealerIdHeader = Annotated[str, Header(alias="X-Dealer-Id")]


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
    from_number: str | None
    to_number: str | None
    body: str
    status: str
    twilio_sid: str | None
    created_at: datetime
    delivered_at: datetime | None


@router.post("/messages/send", response_model=SendSmsOut)
async def send(
    payload: SendSmsIn,
    dealer_id: DealerIdHeader,
    db: Annotated[Session, Depends(get_session)],
) -> SendSmsOut:
    lead = db.get(Lead, payload.lead_id)
    if not lead or lead.dealer_id != dealer_id:
        raise HTTPException(404, "lead not found")

    to = payload.to_number
    if not to:
        listing = db.get(Listing, lead.listing_id)
        to = listing.seller_phone if listing else None
    if not to:
        raise HTTPException(400, "no destination number on lead's listing")

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


@router.get("/leads/{lead_id}/messages", response_model=list[MessageOut])
def list_messages(
    lead_id: int,
    dealer_id: DealerIdHeader,
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
# to the URL you configure in the console. These endpoints should be
# guarded by HMAC signature validation (X-Twilio-Signature) before
# going to production. Stubbed here with a TODO.


@router.post("/webhooks/twilio/status")
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


@router.post("/webhooks/twilio/inbound")
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
        db.add(
            Interaction(
                lead_id=lead.id,
                kind=InteractionKind.TEXT.value,
                direction="inbound",
                body=Body,
            )
        )
        lead.updated_at = datetime.now(timezone.utc)

    # Return empty TwiML so Twilio doesn't auto-reply.
    return "<Response></Response>"


def _digits(phone: str | None) -> str:
    if not phone:
        return ""
    return "".join(c for c in phone if c.isdigit())[-10:]
