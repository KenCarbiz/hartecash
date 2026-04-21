from datetime import datetime, timedelta, timezone

from fsbo.enrichment.posting_hour import (
    hour_of_week_slot,
    is_business_hour,
    posting_pattern_signal,
    summarize_histogram,
)
from fsbo.enrichment.seller_graph import (
    max_posting_hour_signal,
    register_listing_identities,
)
from fsbo.models import Listing, SellerIdentity


def _listing(db, **kw):
    base = {
        "source": "facebook_marketplace",
        "url": "http://x",
        "title": "car",
        "classification": "private_seller",
    }
    base.update(kw)
    row = Listing(**base)
    db.add(row)
    db.flush()
    return row


def test_hour_slot():
    # Monday 10am UTC -> weekday=0, hour=10 -> slot 10
    monday_10am = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    assert hour_of_week_slot(monday_10am) == 10
    # Sunday 2am -> weekday=6, hour=2 -> slot 146
    sunday_2am = datetime(2026, 4, 19, 2, 0, tzinfo=timezone.utc)
    assert hour_of_week_slot(sunday_2am) == 6 * 24 + 2


def test_is_business_hour():
    # Monday 10am = business; Monday 7pm = not; Saturday 10am = not
    assert is_business_hour(10)  # Mon 10
    assert not is_business_hour(19)  # Mon 19 (7pm)
    assert not is_business_hour(5 * 24 + 10)  # Saturday 10am
    assert not is_business_hour(6 * 24 + 10)  # Sunday 10am


def test_summarize_empty():
    s = summarize_histogram({})
    assert s["total"] == 0
    assert s["business_hours_share"] == 0.0


def test_posting_signal_day_job_pattern():
    # 10 listings, 9 weekday business hours = 90% biz share -> -10
    hist = {10: 3, 11: 3, 13: 3, 6 * 24 + 11: 1}  # Sun 11am (not biz)
    summary = summarize_histogram(hist)
    assert posting_pattern_signal(summary) == -10


def test_posting_signal_authentic_private():
    # Evenings + weekends dominate
    hist = {20: 3, 21: 2, 5 * 24 + 14: 2, 6 * 24 + 10: 1}  # Mon 8pm, Mon 9pm, Sat 2pm, Sun 10am
    summary = summarize_histogram(hist)
    assert posting_pattern_signal(summary) == 2


def test_posting_signal_too_few_samples():
    hist = {10: 1, 11: 1}  # only 2 posts
    summary = summarize_histogram(hist)
    assert posting_pattern_signal(summary) == 0


def test_max_posting_hour_signal_integration(db_session):
    # Seed 6 listings all at Mon 10am (business hours) with the same phone
    base = datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc)
    listings = []
    for i in range(6):
        listing = _listing(
            db_session,
            external_id=f"fb-biz-{i}",
            seller_phone="(555) 200-0001",
            posted_at=base + timedelta(minutes=i),
        )
        register_listing_identities(db_session, listing)
        listings.append(listing)

    # Check the identity's histogram
    ident = (
        db_session.query(SellerIdentity)
        .filter_by(kind="phone", value="5552000001")
        .first()
    )
    assert sum(int(v) for v in ident.hour_histogram.values()) == 6

    # The 6th listing's signal should be strong-negative (day-job).
    assert max_posting_hour_signal(db_session, listings[-1].id) == -10


def test_evening_pattern_gives_small_positive(db_session):
    # 5 listings all on Sat afternoon / Sun morning = weekend pattern
    base = datetime(2026, 4, 18, 14, 0, tzinfo=timezone.utc)  # Saturday
    listings = []
    for i in range(5):
        listing = _listing(
            db_session,
            external_id=f"fb-eve-{i}",
            seller_phone="(555) 300-0002",
            posted_at=base + timedelta(hours=i * 3),
        )
        register_listing_identities(db_session, listing)
        listings.append(listing)
    assert max_posting_hour_signal(db_session, listings[-1].id) == 2
