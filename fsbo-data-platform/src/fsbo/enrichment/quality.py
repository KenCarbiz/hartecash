"""Lead quality score (0..100).

Research-backed multi-factor model. Each factor is bounded and contributes
an explainable delta to the base score. The factor breakdown is stored on
the listing so the UI can show "why" a lead scored where it did.

Designed to be cheap (pure function of the listing row + simple market
context) so it can be recomputed on ingest and on nightly rescores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypedDict

from fsbo.enrichment.vin_checksum import valid_vin


class MarketContext(TypedDict, total=False):
    median: float | None
    sample_size: int
    avg_miles_for_age: float | None


@dataclass
class QualityResult:
    score: int
    breakdown: dict[str, int]


def score_listing(
    listing,
    market: MarketContext | None = None,
    phone_listing_count: int = 0,
    dealer_likelihood: float | None = None,
    scam_score: float | None = None,
    price_drops: int = 0,
    days_on_market: int | None = None,
    now: datetime | None = None,
) -> QualityResult:
    """Compute a 0..100 lead quality score.

    Args:
      listing: anything with attrs year, mileage, price, vin, posted_at,
               first_seen_at, images. Works on both SQLAlchemy Listing rows
               and NormalizedListing dataclasses.
      market:  MarketContext dict. median/p25/p75 used for price-vs-market.
      phone_listing_count: how many *other* active listings share this phone.
      dealer_likelihood: 0..1 from dealer_signals.assess().
      scam_score: 0..1 from dealer_signals.assess().
      price_drops: count of observed price decreases on this listing.
      days_on_market: age in days since original posting.
      now: optional clock for determinism in tests.
    """
    now = now or datetime.now(timezone.utc)
    bd: dict[str, int] = {"base": 50}

    # --- Market price signal: below = buyable ---
    price = getattr(listing, "price", None)
    median = (market or {}).get("median")
    if price and median and median > 0:
        delta = (price - median) / median
        pts = int(max(-20, min(20, -delta * 100)))  # 10% under = +10
        bd["price_vs_market"] = pts

    # --- Age sweet spot (3-8 years) ---
    year = getattr(listing, "year", None)
    if year:
        age = now.year - year
        if 3 <= age <= 8:
            bd["age_sweet_spot"] = 5
        elif age > 15:
            bd["age_sweet_spot"] = -5

    # --- Mileage vs age ---
    mileage = getattr(listing, "mileage", None)
    if year and mileage:
        age = max(1, now.year - year)
        expected = age * 12000  # ~12k/year average
        if mileage < expected * 0.8:
            bd["mileage_vs_age"] = 5
        elif mileage > expected * 1.4:
            bd["mileage_vs_age"] = -5

    # --- VIN provided + valid (trust signal) ---
    vin = getattr(listing, "vin", None)
    if vin and valid_vin(vin):
        bd["vin_present"] = 5
    elif vin:
        bd["vin_present"] = 2  # provided but didn't pass checksum

    # --- Images quantity ---
    images = getattr(listing, "images", None) or []
    if len(images) >= 5:
        bd["image_count"] = 5
    elif len(images) == 0:
        bd["image_count"] = -5

    # --- Days on market: research shows 7-30 days is ripe, 60+ is stale ---
    # Prefer explicit days_on_market; fall back to posted_at/first_seen_at.
    dom = days_on_market
    if dom is None:
        posted_at = getattr(listing, "posted_at", None) or getattr(
            listing, "first_seen_at", None
        )
        if posted_at:
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            dom = int((now - posted_at).total_seconds() / 86400)
    if dom is not None:
        if dom <= 0:  # brand new — call first
            bd["days_on_market"] = 15
        elif dom <= 3:
            bd["days_on_market"] = 10
        elif dom <= 7:
            bd["days_on_market"] = 5
        elif dom <= 30:
            bd["days_on_market"] = 3  # ripe window: seller may be getting motivated
        elif dom <= 60:
            bd["days_on_market"] = -3
        else:
            bd["days_on_market"] = -10  # stale / likely sold or ghost

    # --- Price drops: motivated seller signal ---
    if price_drops >= 3:
        bd["price_drops"] = 12
    elif price_drops == 2:
        bd["price_drops"] = 8
    elif price_drops == 1:
        bd["price_drops"] = 5

    # --- Dealer risk penalty ---
    if dealer_likelihood is not None:
        if dealer_likelihood >= 0.7:
            bd["dealer_risk"] = -40
        elif dealer_likelihood >= 0.4:
            bd["dealer_risk"] = -15

    # --- Scam risk penalty ---
    if scam_score is not None and scam_score >= 0.6:
        bd["scam_risk"] = -30

    # --- Curbstoner: phone appears on many listings ---
    if phone_listing_count >= 5:
        bd["phone_cross_listing"] = -15
    elif phone_listing_count >= 3:
        bd["phone_cross_listing"] = -8

    # --- Phone provided at all (signal of a real seller) ---
    if getattr(listing, "seller_phone", None):
        bd["phone_provided"] = 3

    total = sum(bd.values())
    total = max(0, min(100, total))
    return QualityResult(score=total, breakdown=bd)
