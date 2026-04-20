"""Phone-number cross-listing graph.

Curbstoners (unlicensed dealers posing as private sellers) tend to post
many listings from the same phone number, often across multiple cities
and profile names. A phone appearing on 3+ active listings in 30 days is
a strong curbstoner signal per Carfax/Bumper research.
"""

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.models import Listing


def normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def count_other_listings(
    db: Session,
    phone: str | None,
    exclude_id: int | None = None,
    within_days: int = 30,
) -> int:
    normalized = normalize_phone(phone)
    if not normalized:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    stmt = select(Listing.id).where(
        Listing.seller_phone.is_not(None),
        Listing.first_seen_at >= cutoff,
    )
    if exclude_id is not None:
        stmt = stmt.where(Listing.id != exclude_id)
    candidates = db.scalars(stmt).all()
    # Re-normalize stored phones in-app since we don't want to migrate
    # historical data. In production we'd add a stored normalized column.
    count = 0
    for lid in candidates:
        row = db.get(Listing, lid)
        if row and normalize_phone(row.seller_phone) == normalized:
            count += 1
    return count
