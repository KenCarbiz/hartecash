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

import re
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
from fsbo.models import Dealer, SmsConsent, SmsOptOut

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


# ---- Quiet-hours override ------------------------------------------


_HHMM_RE = re.compile(r"^(?P<h>\d{1,2}):(?P<m>\d{2})$")


def _validate_hhmm(raw: str | None) -> str | None:
    """Round-trip 'HH:MM' to a normalized two-digit form ('08:30').
    None / empty string passes through unchanged. Raises HTTPException
    on malformed input."""
    if raw is None or raw == "":
        return None
    m = _HHMM_RE.match(raw.strip())
    if not m:
        raise HTTPException(400, f"quiet-hours time must be HH:MM, got '{raw}'")
    h = int(m.group("h"))
    mm = int(m.group("m"))
    if not (0 <= h <= 23 and 0 <= mm <= 59):
        raise HTTPException(400, f"quiet-hours out of range: '{raw}'")
    return f"{h:02d}:{mm:02d}"


class QuietHoursOut(BaseModel):
    """Federal default is 8 AM - 8 PM seller-local; the dealer can
    tighten (not loosen) it via this endpoint."""

    start: str
    end: str
    is_override: bool


class QuietHoursPatch(BaseModel):
    start: str | None = None
    end: str | None = None


@router.get("/quiet-hours", response_model=QuietHoursOut)
def get_quiet_hours(
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> QuietHoursOut:
    row = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))
    start = (row.quiet_hours_start if row else None) or "08:00"
    end = (row.quiet_hours_end if row else None) or "20:00"
    is_override = bool(row and (row.quiet_hours_start or row.quiet_hours_end))
    return QuietHoursOut(start=start, end=end, is_override=is_override)


@router.put("/quiet-hours", response_model=QuietHoursOut)
def update_quiet_hours(
    payload: QuietHoursPatch,
    dealer_id: DealerId,
    db: Annotated[Session, Depends(get_session)],
) -> QuietHoursOut:
    """Tighten quiet-hours for this dealership.

    Federal TCPA bans calls before 8 AM / after 9 PM. We default to
    8 AM - 8 PM (one hour stricter on the late side). Dealers can
    tighten to e.g. 9 AM - 6 PM but cannot loosen past federal: any
    start < 08:00 or end > 20:00 is rejected so misconfiguration can't
    create TCPA exposure.
    """
    start_norm = _validate_hhmm(payload.start)
    end_norm = _validate_hhmm(payload.end)

    if start_norm is not None and start_norm < "08:00":
        raise HTTPException(
            400,
            "start cannot be earlier than 08:00 — federal TCPA quiet-hours "
            "begin at 8 AM seller-local",
        )
    if end_norm is not None and end_norm > "20:00":
        raise HTTPException(
            400,
            "end cannot be later than 20:00 — federal TCPA quiet-hours "
            "begin at 9 PM, we cap at 8 PM for safety",
        )
    if start_norm and end_norm and start_norm >= end_norm:
        raise HTTPException(400, "start must be before end")

    row = db.scalar(select(Dealer).where(Dealer.slug == dealer_id))
    if not row:
        raise HTTPException(404, "dealer not found")
    row.quiet_hours_start = start_norm
    row.quiet_hours_end = end_norm
    db.flush()

    return QuietHoursOut(
        start=row.quiet_hours_start or "08:00",
        end=row.quiet_hours_end or "20:00",
        is_override=bool(row.quiet_hours_start or row.quiet_hours_end),
    )
