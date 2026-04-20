"""Lead quality score (0..100).

Research-backed multi-factor model. Each factor is bounded and contributes
an explainable delta to the base score. The factor breakdown is stored on
the listing so the UI can show "why" a lead scored where it did.

Thresholds (see dealer_ui):
  >= 80  Hot     — call within 2 hours
  65-79  Warm    — call within 24h
  45-64  Monitor — watch for price drops
  25-44  Cold    — filter out by default
   < 25  Reject  — auto-hide

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
    auto_hide: bool = False
    auto_hide_reason: str | None = None


HOT_THRESHOLD = 80
WARM_THRESHOLD = 65
MONITOR_THRESHOLD = 45
COLD_THRESHOLD = 25


def score_listing(
    listing,
    market: MarketContext | None = None,
    phone_listing_count: int = 0,
    dealer_likelihood: float | None = None,
    scam_score: float | None = None,
    price_drops: int = 0,
    days_on_market: int | None = None,
    relist_detected: bool = False,
    vin_vpic_mismatch: bool = False,
    title_brand: str | None = None,
    price_velocity_per_day: float = 0.0,
    authenticity_score: int = 0,
    phone_line_type_score: int = 0,
    now: datetime | None = None,
) -> QualityResult:
    """Compute a 0..100 lead quality score + auto-hide verdict.

    New (2026 research-upgrade):
      - days_on_market now peaks at the 21-35 day motivation window
      - price_drops weights bumped: 1/5, 2/10, 3+/15
      - relist_detected (+8), life_event (+4), registration_expiring (+3),
        end_of_month posting (+2) from listing.raw.attributes.
      - vin_vpic_mismatch: -25 free signal (NHTSA decode disagrees with
        listed year/make).
      - title_brand: paid NMVTIS-confirmed brand; -35 if branded salvage/
        rebuilt/flood/lemon; auto_hide for junk/theft_reported.
      - Hard-reject rules set auto_hide=True so the /listings endpoint
        can exclude them from default dealer views.
    """
    now = now or datetime.now(timezone.utc)
    bd: dict[str, int] = {"base": 50}
    auto_hide = False
    auto_hide_reason: str | None = None

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
        bd["vin_valid"] = 5
    elif vin:
        bd["vin_invalid_checksum"] = -3  # provided but checksum fails — data entry or scam

    # --- VIN / vPIC brand+year mismatch (free, high-signal fraud flag) ---
    if vin_vpic_mismatch:
        bd["vin_vpic_mismatch"] = -25

    # --- Images quantity ---
    images = getattr(listing, "images", None) or []
    if len(images) >= 10:
        bd["image_count"] = 8
    elif len(images) >= 5:
        bd["image_count"] = 5
    elif len(images) == 0:
        bd["image_count"] = -5

    # --- Days on market: peak motivation window is 21-35 days ---
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
        if dom <= 0:
            bd["days_on_market"] = 12
        elif dom <= 3:
            bd["days_on_market"] = 8
        elif dom <= 7:
            bd["days_on_market"] = 4
        elif dom <= 20:
            bd["days_on_market"] = 6
        elif dom <= 35:
            bd["days_on_market"] = 10  # PEAK motivation
        elif dom <= 60:
            bd["days_on_market"] = 6
        elif dom <= 90:
            bd["days_on_market"] = -3
        else:
            bd["days_on_market"] = -10

    # --- Price drops: motivated seller signal (compounded weights) ---
    if price_drops >= 3:
        bd["price_drops"] = 15
    elif price_drops == 2:
        bd["price_drops"] = 10
    elif price_drops == 1:
        bd["price_drops"] = 5

    # --- Relist detection: came back after a gap = motivated ---
    if relist_detected:
        bd["relist_detected"] = 8

    # --- Price velocity: aggressive drop rate = urgent seller ---
    # $50/day+ = actively reducing price every week or two.
    if price_velocity_per_day >= 100:
        bd["price_velocity"] = 8
    elif price_velocity_per_day >= 50:
        bd["price_velocity"] = 5
    elif price_velocity_per_day >= 20:
        bd["price_velocity"] = 2

    # --- Authenticity (typos + colloquialisms = real human) ---
    if authenticity_score > 0:
        bd["authenticity"] = min(5, authenticity_score)
    elif authenticity_score < 0:
        # Corporate/AI-boilerplate phrasing penalty
        bd["boilerplate_copy"] = max(-5, authenticity_score)

    # --- End-of-month timing: car-payment-due motivation ---
    if now.day >= 28:
        bd["end_of_month"] = 2

    # --- Dealer risk penalty ---
    if dealer_likelihood is not None:
        if dealer_likelihood >= 0.85:
            auto_hide = True
            auto_hide_reason = "dealer_likelihood>=0.85"
            bd["dealer_risk"] = -40
        elif dealer_likelihood >= 0.7:
            bd["dealer_risk"] = -30
        elif dealer_likelihood >= 0.4:
            bd["dealer_risk"] = -15

    # --- Scam risk penalty (tiered by tiered scam_score) ---
    if scam_score is not None:
        if scam_score >= 0.9:
            auto_hide = True
            auto_hide_reason = auto_hide_reason or "scam_score>=0.9"
            bd["scam_risk"] = -50
        elif scam_score >= 0.7:
            bd["scam_risk"] = -30
        elif scam_score >= 0.45:
            bd["scam_risk"] = -15

    # --- Curbstoner: phone appears on many listings ---
    if phone_listing_count >= 10:
        auto_hide = True
        auto_hide_reason = auto_hide_reason or "phone_on_10plus_listings"
        bd["phone_cross_listing"] = -25
    elif phone_listing_count >= 5:
        bd["phone_cross_listing"] = -15
    elif phone_listing_count >= 3:
        bd["phone_cross_listing"] = -8

    # --- Phone provided at all (signal of a real seller) ---
    if getattr(listing, "seller_phone", None):
        bd["phone_provided"] = 3

    # --- Carrier / line-type (VoIP = scam tell; mobile = authentic) ---
    if phone_line_type_score:
        bd["phone_line_type"] = phone_line_type_score

    # --- Confirmed title brand (paid NMVTIS check) ---
    if title_brand:
        if title_brand in ("junk", "theft_reported"):
            auto_hide = True
            auto_hide_reason = auto_hide_reason or f"title_brand={title_brand}"
            bd["title_brand_hard"] = -50
        elif title_brand in ("salvage", "rebuilt", "flood", "lemon"):
            bd["title_brand_branded"] = -35
        elif title_brand == "clean":
            bd["title_brand_clean"] = 5

    # --- Attribute-derived signals from the raw-text extractor ---
    raw = getattr(listing, "raw", {}) or {}
    attrs = raw.get("attributes") if isinstance(raw, dict) else None
    if isinstance(attrs, dict):
        # If we haven't had a confirmed title check, the free regex-detected
        # title gives a conservative penalty (supplanted by title_brand if set).
        if not title_brand:
            title_type = attrs.get("title_type")
            if title_type in ("salvage", "rebuilt", "flood", "lemon"):
                bd["title_text_risk"] = -15
            elif title_type == "clean":
                bd["title_text_clean"] = 3
        if attrs.get("owner_count") == 1:
            bd["one_owner"] = 3
        if attrs.get("has_service_records"):
            bd["service_records"] = 2
        if attrs.get("accident_mentioned"):
            bd["accident_free"] = 2
        if attrs.get("negotiable") is True:
            bd["negotiable"] = 4
        if attrs.get("life_event"):
            bd["life_event"] = 4
        if attrs.get("registration_expiring"):
            bd["registration_expiring"] = 3

    total = sum(bd.values())
    total = max(0, min(100, total))
    return QualityResult(
        score=total,
        breakdown=bd,
        auto_hide=auto_hide,
        auto_hide_reason=auto_hide_reason,
    )


def verdict_for_score(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score >= HOT_THRESHOLD:
        return "hot"
    if score >= WARM_THRESHOLD:
        return "warm"
    if score >= MONITOR_THRESHOLD:
        return "monitor"
    if score >= COLD_THRESHOLD:
        return "cold"
    return "reject"
