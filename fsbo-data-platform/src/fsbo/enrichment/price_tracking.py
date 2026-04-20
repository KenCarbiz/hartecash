"""Price change tracking.

Called from the upsert flow. When we see a listing whose price has changed
since the last observation, we log a PriceHistory row. Drops are used as a
motivated-seller signal in the quality score; increases get counted too but
don't affect scoring.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.models import Listing, PriceHistory


def record_price(db: Session, listing: Listing, new_price: float | None) -> bool:
    """Compare new_price to the most recent observed price for this listing.
    Returns True if a new PriceHistory row was written.
    """
    if new_price is None or new_price <= 0:
        return False

    last = db.scalar(
        select(PriceHistory)
        .where(PriceHistory.listing_id == listing.id)
        .order_by(PriceHistory.observed_at.desc())
        .limit(1)
    )
    if last and abs(float(last.price) - new_price) < 1:
        return False  # unchanged (within rounding)

    delta = None
    if last:
        delta = new_price - float(last.price)
    db.add(
        PriceHistory(
            listing_id=listing.id,
            price=new_price,
            delta=delta,
            observed_at=datetime.now(timezone.utc),
        )
    )
    return True


def count_drops(db: Session, listing_id: int) -> int:
    """Number of observed price decreases on this listing."""
    rows = db.scalars(
        select(PriceHistory.delta).where(PriceHistory.listing_id == listing_id)
    ).all()
    return sum(1 for d in rows if d is not None and d < 0)


def last_price_change_at(db: Session, listing_id: int) -> datetime | None:
    last = db.scalar(
        select(PriceHistory)
        .where(PriceHistory.listing_id == listing_id)
        .order_by(PriceHistory.observed_at.desc())
        .limit(1)
    )
    return last.observed_at if last else None
