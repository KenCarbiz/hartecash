"""Peer-based market value estimation.

This is our lightweight alternative to vAuto / MMR / KBB integration for
dealers who don't have (or don't pay for) a Cox Automotive subscription.

We compute a robust central tendency (trimmed median) of comparable
listings in the dataset, plus an inter-quartile range to show "how hot"
the segment is.

Comparable = same make + model; ±2 model years; ±30% mileage; limited
to the same classification (private_seller) to avoid dealer-ask bias.

This isn't MMR — those come from actual wholesale auction data we don't
have access to. But it's a useful anchor for dealers who just want to
know if a specific listing is above or below the private-party market.
"""

from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from fsbo.models import Classification, Listing


@dataclass
class MarketEstimate:
    sample_size: int
    median: float | None
    p25: float | None
    p75: float | None
    listing_price: float | None
    delta_pct: float | None  # listing_price vs median, as a percent
    verdict: str  # below | at | above | unknown


def estimate(db: Session, listing: Listing) -> MarketEstimate:
    if not (listing.make and listing.model and listing.year):
        return _unknown(listing.price)

    year_min = listing.year - 2
    year_max = listing.year + 2
    filters = [
        Listing.id != listing.id,
        Listing.make == listing.make,
        Listing.model == listing.model,
        Listing.year >= year_min,
        Listing.year <= year_max,
        Listing.price.is_not(None),
        Listing.classification == Classification.PRIVATE_SELLER.value,
    ]
    if listing.mileage:
        low = int(listing.mileage * 0.7)
        high = int(listing.mileage * 1.3)
        filters.append(Listing.mileage.between(low, high))

    prices = db.scalars(select(Listing.price).where(and_(*filters))).all()
    if not prices:
        return _unknown(listing.price)

    values = sorted(float(p) for p in prices)
    median_val = _quantile(values, 0.5)
    p25 = _quantile(values, 0.25)
    p75 = _quantile(values, 0.75)

    delta_pct: float | None = None
    verdict = "unknown"
    if listing.price is not None and median_val > 0:
        delta_pct = (listing.price - median_val) / median_val * 100
        if delta_pct < -8:
            verdict = "below"
        elif delta_pct > 8:
            verdict = "above"
        else:
            verdict = "at"

    return MarketEstimate(
        sample_size=len(values),
        median=median_val,
        p25=p25,
        p75=p75,
        listing_price=listing.price,
        delta_pct=delta_pct,
        verdict=verdict,
    )


def _unknown(price: float | None) -> MarketEstimate:
    return MarketEstimate(
        sample_size=0,
        median=None,
        p25=None,
        p75=None,
        listing_price=price,
        delta_pct=None,
        verdict="unknown",
    )


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * q
    lo = int(index)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = index - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac
