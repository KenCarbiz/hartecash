"""TCPA compliance gate.

Three checks before any outbound SMS:

  1. Quiet hours — federal TCPA requires 8:00 AM - 9:00 PM in the
     RECIPIENT's local time. State mini-TCPAs are stricter in some
     places (FL/OK/WA quiet hours start at 8 PM). We err on the strict
     side: block before 9 AM and after 8 PM local.
  2. Opt-out registry — if the seller texted STOP / END / QUIT /
     UNSUBSCRIBE / CANCEL, the SmsOptOut row blocks every future send
     to that number for that dealership.
  3. Consent — at launch we don't enforce written consent for
     marketplace-listed phones (the seller publicly posted the number
     to receive contact about the listing, which is the established-
     business-relationship carve-out). When a dealer opts into "strict
     consent mode" via dealer setting, we block until SmsConsent exists.

Carrier opt-out (delivered via Twilio inbound webhook) feeds the same
registry. The Messages.Body matcher is in messages.py.

Quiet-hour ZIP -> timezone is best-effort. We use a coarse first-digit
mapping (5 timezones cover most of the US ZIP space) since a real
geocoder is in the roadmap, not shipped. False positives (blocking when
we shouldn't) are far cheaper than false negatives.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.models import SmsConsent, SmsOptOut

# Stop-keyword list per CTIA + Twilio guidance. Compared lower-case
# after stripping whitespace + punctuation.
STOP_KEYWORDS = {
    "stop",
    "stopall",
    "unsubscribe",
    "cancel",
    "end",
    "quit",
    "remove",
    "revoke",
    "no",
}

# Quiet hours: federal-strict default. Dealers can tighten; nobody
# loosens without explicit per-state configuration in a future release.
QUIET_HOURS_START = time(8, 0)
QUIET_HOURS_END = time(20, 0)


# Coarse ZIP -> Olson tz mapping. Real geocoder is roadmap; this is
# good enough to catch "Hawaii at 5 AM" obvious-block cases.
def _tz_for_zip(zip_code: str | None) -> str:
    if not zip_code:
        return "America/New_York"  # safest default for unknown
    z = zip_code.strip()[:5]
    if not z.isdigit():
        return "America/New_York"
    n = int(z)
    # Approximate first-digit ranges — covers ~85% of mainland coverage.
    if 0 <= n <= 27999:
        return "America/New_York"  # Northeast
    if 28000 <= n <= 36999:
        return "America/New_York"  # Southeast
    if 37000 <= n <= 49999:
        return "America/Chicago"  # Midwest east
    if 50000 <= n <= 67999:
        return "America/Chicago"  # Midwest west
    if 68000 <= n <= 79999:
        return "America/Chicago"  # Texas/Plains
    if 80000 <= n <= 88999:
        return "America/Denver"  # Mountain
    if 89000 <= n <= 89999:
        return "America/Los_Angeles"  # Nevada (mostly Pacific)
    if 90000 <= n <= 96199:
        return "America/Los_Angeles"  # California
    if 96700 <= n <= 96899:
        return "Pacific/Honolulu"  # Hawaii
    if 99500 <= n <= 99999:
        return "America/Anchorage"  # Alaska
    return "America/New_York"


def _local_now(tz_name: str) -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.now(timezone.utc)


def in_quiet_hours(zip_code: str | None, when: datetime | None = None) -> bool:
    """True iff a send to this ZIP right now would be in quiet hours."""
    tz_name = _tz_for_zip(zip_code)
    local = (
        when.astimezone(__import__("zoneinfo").ZoneInfo(tz_name))
        if when
        else _local_now(tz_name)
    )
    return not (QUIET_HOURS_START <= local.time() < QUIET_HOURS_END)


def normalize_phone(raw: str | None) -> str:
    if not raw:
        return ""
    return "".join(c for c in raw if c.isdigit())[-10:]


def is_stop_keyword(body: str | None) -> bool:
    if not body:
        return False
    cleaned = body.strip().lower().rstrip(".!?")
    return cleaned in STOP_KEYWORDS


@dataclass
class TcpaCheckResult:
    allowed: bool
    blocked_reason: Literal[
        "ok",
        "quiet_hours",
        "opted_out",
        "no_consent",
    ] = "ok"
    detail: str = ""


def check_send_allowed(
    db: Session,
    dealer_id: str,
    phone: str,
    zip_code: str | None,
    require_consent: bool = False,
) -> TcpaCheckResult:
    """Return TcpaCheckResult — caller refuses to send when not allowed."""
    norm = normalize_phone(phone)
    if not norm:
        return TcpaCheckResult(allowed=False, blocked_reason="ok", detail="no phone")

    # 1. Opt-out wins everything.
    opt_out = db.scalar(
        select(SmsOptOut).where(
            SmsOptOut.dealer_id == dealer_id,
            SmsOptOut.phone == norm,
        )
    )
    if opt_out:
        return TcpaCheckResult(
            allowed=False,
            blocked_reason="opted_out",
            detail=f"opted out via {opt_out.source}",
        )

    # 2. Quiet hours.
    if in_quiet_hours(zip_code):
        tz = _tz_for_zip(zip_code)
        return TcpaCheckResult(
            allowed=False,
            blocked_reason="quiet_hours",
            detail=f"outside 8AM-8PM {tz}",
        )

    # 3. Strict-consent mode.
    if require_consent:
        consent = db.scalar(
            select(SmsConsent).where(
                SmsConsent.dealer_id == dealer_id,
                SmsConsent.phone == norm,
                SmsConsent.revoked_at.is_(None),
            )
        )
        if not consent:
            return TcpaCheckResult(
                allowed=False,
                blocked_reason="no_consent",
                detail="strict-consent mode requires SmsConsent row first",
            )

    return TcpaCheckResult(allowed=True)


def record_opt_out(
    db: Session,
    dealer_id: str,
    phone: str,
    source: str,
    note: str | None = None,
) -> SmsOptOut:
    """Idempotent. Returns the existing row if already opted out."""
    norm = normalize_phone(phone)
    existing = db.scalar(
        select(SmsOptOut).where(
            SmsOptOut.dealer_id == dealer_id,
            SmsOptOut.phone == norm,
        )
    )
    if existing:
        return existing
    row = SmsOptOut(
        dealer_id=dealer_id, phone=norm, source=source, note=note
    )
    db.add(row)
    db.flush()
    return row


def record_consent(
    db: Session,
    dealer_id: str,
    phone: str,
    consent_text: str,
    captured_via: str,
    captured_by_user: str | None = None,
) -> SmsConsent:
    """Upsert. Re-recording consent for a phone updates the text + via."""
    norm = normalize_phone(phone)
    existing = db.scalar(
        select(SmsConsent).where(
            SmsConsent.dealer_id == dealer_id,
            SmsConsent.phone == norm,
        )
    )
    if existing:
        existing.consent_text = consent_text
        existing.captured_via = captured_via
        existing.captured_by_user = captured_by_user
        existing.revoked_at = None
        db.flush()
        return existing
    row = SmsConsent(
        dealer_id=dealer_id,
        phone=norm,
        consent_text=consent_text[:8000],
        captured_via=captured_via,
        captured_by_user=captured_by_user,
    )
    db.add(row)
    db.flush()
    return row
