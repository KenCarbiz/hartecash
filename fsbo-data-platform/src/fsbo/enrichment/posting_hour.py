"""Posting-hour fingerprint (day-job detection).

Private sellers post evenings + weekends — typical distribution is
bimodal around lunch hour and 6-10pm weekdays, plus all-day weekends.
A dealer or curbstoner with a listing operation posts during business
hours (M-F 9am-6pm local). If the same seller identity (phone, email,
image hash cluster) accounts for multiple listings and those listings
skew business-hours, we have a strong dealer tell.

We store a 168-slot histogram (7 days × 24 hours) per SellerIdentity,
incremented every time a new listing is registered. The scorer queries
the shape of that histogram.

The scoring signal:
  business_hours_share >= 0.80 with >= 5 listings -> -10 pts
  business_hours_share >= 0.65 with >= 5 listings -> -5 pts
  evening_or_weekend_share >= 0.70 with >= 3 listings -> +2 pts (authenticity)

"Business hours" = Mon-Fri, 9am-5pm local (we use listing's local
timezone when we have it; otherwise UTC offset is good-enough for
coarse bucketing).
"""

from __future__ import annotations

from datetime import datetime, timezone

# Hour-of-week slot = day_of_week * 24 + hour_of_day (0-167)
BUSINESS_HOUR_START = 9
BUSINESS_HOUR_END = 17  # exclusive; so 9-16 inclusive
WEEKDAY_MAX = 5  # Mon-Fri are 0-4 in Python's datetime.weekday()


def hour_of_week_slot(when: datetime | None) -> int | None:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.weekday() * 24 + when.hour


def is_business_hour(slot: int) -> bool:
    dow, hour = divmod(slot, 24)
    return dow < WEEKDAY_MAX and BUSINESS_HOUR_START <= hour < BUSINESS_HOUR_END


def summarize_histogram(hist: dict[int, int]) -> dict[str, float | int]:
    """Return shares + tags for a seller-identity hour-of-week histogram."""
    if not hist:
        return {"total": 0, "business_hours_share": 0.0, "evening_weekend_share": 0.0}

    total = sum(hist.values())
    biz = sum(count for slot, count in hist.items() if is_business_hour(slot))
    # "Evenings" = weekday 18-23 or any weekend hour
    def _is_evening_or_weekend(slot: int) -> bool:
        dow, hour = divmod(slot, 24)
        if dow >= WEEKDAY_MAX:
            return True
        return hour >= 18 or hour < 7
    eve = sum(count for slot, count in hist.items() if _is_evening_or_weekend(slot))

    return {
        "total": total,
        "business_hours_share": biz / total,
        "evening_weekend_share": eve / total,
    }


def posting_pattern_signal(
    summary: dict[str, float | int],
) -> int:
    """Return a quality-score contribution based on the summary shape.

    Only signals when we have >=3 samples; below that the shape is too
    noisy to trust.
    """
    total = int(summary.get("total", 0) or 0)
    if total < 3:
        return 0

    biz = float(summary.get("business_hours_share", 0) or 0)
    eve = float(summary.get("evening_weekend_share", 0) or 0)

    if total >= 5 and biz >= 0.80:
        return -10  # strong day-job pattern -> dealer/curbstoner
    if total >= 5 and biz >= 0.65:
        return -5
    if total >= 3 and eve >= 0.70:
        return 2  # looks authentic private-seller pattern
    return 0
