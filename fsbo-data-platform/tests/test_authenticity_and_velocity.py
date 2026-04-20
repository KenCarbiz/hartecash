from datetime import datetime, timedelta, timezone

from fsbo.enrichment.authenticity import score_authenticity
from fsbo.enrichment.price_tracking import price_velocity_per_day, record_price
from fsbo.models import Listing, PriceHistory


def test_typos_boost_authenticity():
    txt = "Its a great car, runs like a top, cant beat it, no BS. First come first serve."
    r = score_authenticity(txt)
    assert r["typo_hits"] >= 1
    assert r["colloquial_hits"] >= 2
    assert r["authenticity_score"] > 0


def test_corporate_copy_penalized():
    txt = (
        "This vehicle is in excellent condition. Please feel free to contact us "
        "at your earliest convenience. We are pleased to offer this automobile."
    )
    r = score_authenticity(txt)
    assert r["corporate_hits"] >= 2
    assert r["authenticity_score"] < 0


def test_empty_description():
    r = score_authenticity(None)
    assert r["authenticity_score"] == 0
    r = score_authenticity("")
    assert r["authenticity_score"] == 0


def test_authenticity_clamped():
    # Lots of typos + colloquialisms — clamped to +5
    txt = (
        "Its a beater but runs like a top. Cant beat the price. "
        "Im selling cuz my wifes getting a new one. Lol. No BS. "
        "Grandma's car. Tommorrow works if ya know."
    )
    r = score_authenticity(txt)
    assert r["authenticity_score"] <= 5


def test_price_velocity_zero_when_unchanged(db_session):
    listing = Listing(
        source="test",
        external_id="x",
        url="http://x",
        price=20000,
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    record_price(db_session, listing, 20000)
    # Only one price point → velocity is 0
    assert price_velocity_per_day(db_session, listing.id) == 0.0


def test_price_velocity_positive_when_dropping(db_session):
    listing = Listing(
        source="test",
        external_id="x",
        url="http://x",
        price=20000,
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()

    old = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.add(
        PriceHistory(listing_id=listing.id, price=22000, observed_at=old)
    )
    db_session.add(
        PriceHistory(
            listing_id=listing.id,
            price=20000,
            delta=-2000,
            observed_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()

    v = price_velocity_per_day(db_session, listing.id)
    # $2000 drop over 10 days = $200/day
    assert 190 <= v <= 210
