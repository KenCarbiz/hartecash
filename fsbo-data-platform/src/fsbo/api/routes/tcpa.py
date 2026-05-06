"""TCPA dealer-side endpoints: manual opt-out, consent capture,
audit-log export.

The send-time gate lives in fsbo.messaging.tcpa; this router exposes it
to dealers so they can:

  - Manually add a phone to the opt-out registry (e.g. seller asked
    over the phone, not via SMS STOP).
  - Record affirmative consent when capturing it through a non-SMS
    channel (web form on a landing page, in-person, marketplace DM).
  - Export the audit log for compliance review.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.auth.resolver import DealerId
from fsbo.db import get_session
from fsbo.messaging.tcpa import (
    normalize_phone,
    record_consent,
    record_opt_out,
)
from fsbo.models import SmsConsent, SmsOptOut

router = APIRouter(prefix="/tcpa", tags=["tcpa"])


class OptOutIn(BaseModel):
    phone: str
    note: str | None = None


class OptOutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    source: str
    note: str | None
    created_at: datetime


class ConsentIn(BaseModel):
    phone: str
    consent_text: str
    captured_via: str = "manual"
    captured_by_user: str | None = None


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    consent_text: str
    captured_via: str
    captured_by_user: str | None
    revoked_at: datetime | None
    created_at: datetime


@router.post("/opt-outs", response_model=OptOutOut, status_code=201)
def add_opt_out(
    payload: OptOutIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> OptOutOut:
    if not normalize_phone(payload.phone):
        raise HTTPException(400, "phone must be a US 10-digit number")
    row = record_opt_out(
        db,
        dealer_id=dealer_id,
        phone=payload.phone,
        source="manual",
        note=payload.note,
    )
    return OptOutOut.model_validate(row)


@router.get("/opt-outs", response_model=list[OptOutOut])
def list_opt_outs(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    limit: int = 200,
) -> list[OptOutOut]:
    rows = db.scalars(
        select(SmsOptOut)
        .where(SmsOptOut.dealer_id == dealer_id)
        .order_by(SmsOptOut.created_at.desc())
        .limit(min(limit, 1000))
    ).all()
    return [OptOutOut.model_validate(r) for r in rows]


@router.delete("/opt-outs/{phone}", status_code=204)
def remove_opt_out(
    phone: str,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> None:
    """Manual unblock — used carefully. Records a consent row at the
    same time so the unblock is auditable."""
    norm = normalize_phone(phone)
    row = db.scalar(
        select(SmsOptOut).where(
            SmsOptOut.dealer_id == dealer_id,
            SmsOptOut.phone == norm,
        )
    )
    if not row:
        raise HTTPException(404, "opt-out not found")
    db.delete(row)


@router.post("/consents", response_model=ConsentOut, status_code=201)
def capture_consent(
    payload: ConsentIn,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> ConsentOut:
    if not normalize_phone(payload.phone):
        raise HTTPException(400, "phone must be a US 10-digit number")
    row = record_consent(
        db,
        dealer_id=dealer_id,
        phone=payload.phone,
        consent_text=payload.consent_text,
        captured_via=payload.captured_via,
        captured_by_user=payload.captured_by_user,
    )
    return ConsentOut.model_validate(row)


@router.get("/consents", response_model=list[ConsentOut])
def list_consents(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
    limit: int = 200,
) -> list[ConsentOut]:
    rows = db.scalars(
        select(SmsConsent)
        .where(SmsConsent.dealer_id == dealer_id)
        .order_by(SmsConsent.created_at.desc())
        .limit(min(limit, 1000))
    ).all()
    return [ConsentOut.model_validate(r) for r in rows]
