from datetime import datetime, timezone

from fsbo.enrichment.quality import (
    COLD_THRESHOLD,
    HOT_THRESHOLD,
    MONITOR_THRESHOLD,
    WARM_THRESHOLD,
    score_listing,
    verdict_for_score,
)


class MockListing:
    def __init__(self, **kwargs):
        self.year = kwargs.get("year")
        self.mileage = kwargs.get("mileage")
        self.price = kwargs.get("price")
        self.vin = kwargs.get("vin")
        self.posted_at = kwargs.get("posted_at")
        self.first_seen_at = kwargs.get("first_seen_at")
        self.images = kwargs.get("images", [])
        self.seller_phone = kwargs.get("seller_phone")
        self.raw = kwargs.get("raw", {})


NOW = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)


def test_dom_peak_at_21_to_35():
    # At day 25 we should be at peak motivation (+10)
    result = score_listing(MockListing(year=2020, images=["a.jpg"] * 5), days_on_market=25, now=NOW)
    assert result.breakdown["days_on_market"] == 10


def test_dom_stale_at_75():
    result = score_listing(MockListing(year=2020, images=["a.jpg"] * 5), days_on_market=75, now=NOW)
    assert result.breakdown["days_on_market"] == -3


def test_price_drops_compound():
    listing = MockListing(year=2020, images=["a.jpg"] * 5)
    one = score_listing(listing, price_drops=1, now=NOW).breakdown["price_drops"]
    two = score_listing(listing, price_drops=2, now=NOW).breakdown["price_drops"]
    three = score_listing(listing, price_drops=3, now=NOW).breakdown["price_drops"]
    assert one == 5 and two == 10 and three == 15


def test_relist_detected_adds_signal():
    result = score_listing(
        MockListing(year=2020, images=["a.jpg"] * 3),
        relist_detected=True,
        now=NOW,
    )
    assert result.breakdown.get("relist_detected") == 8


def test_end_of_month_signal():
    eom = datetime(2026, 4, 29, 10, 0, tzinfo=timezone.utc)
    not_eom = datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc)
    listing = MockListing(year=2020, images=["a.jpg"] * 3)
    assert score_listing(listing, now=eom).breakdown.get("end_of_month") == 2
    assert "end_of_month" not in score_listing(listing, now=not_eom).breakdown


def test_scam_09_triggers_auto_hide():
    result = score_listing(
        MockListing(year=2020, images=["a.jpg"] * 3),
        scam_score=0.95,
        now=NOW,
    )
    assert result.auto_hide is True
    assert "scam" in (result.auto_hide_reason or "")


def test_dealer_085_triggers_auto_hide():
    result = score_listing(
        MockListing(year=2020, images=["a.jpg"] * 3),
        dealer_likelihood=0.9,
        now=NOW,
    )
    assert result.auto_hide is True
    assert "dealer" in (result.auto_hide_reason or "")


def test_phone_10plus_triggers_auto_hide():
    result = score_listing(
        MockListing(year=2020, images=["a.jpg"] * 3),
        phone_listing_count=12,
        now=NOW,
    )
    assert result.auto_hide is True


def test_title_junk_auto_hides():
    result = score_listing(
        MockListing(year=2020, images=["a.jpg"] * 3),
        title_brand="junk",
        now=NOW,
    )
    assert result.auto_hide is True


def test_title_salvage_heavy_penalty_but_not_hide():
    result = score_listing(
        MockListing(year=2020, images=["a.jpg"] * 3),
        title_brand="salvage",
        now=NOW,
    )
    assert result.auto_hide is False
    assert result.breakdown["title_brand_branded"] == -35


def test_vpic_mismatch_flag():
    result = score_listing(
        MockListing(year=2020, make="Ford", images=["a.jpg"] * 3),
        vin_vpic_mismatch=True,
        now=NOW,
    )
    assert result.breakdown["vin_vpic_mismatch"] == -25


def test_life_event_signals():
    result = score_listing(
        MockListing(
            year=2020,
            images=["a.jpg"] * 3,
            raw={"attributes": {"life_event": "moving", "registration_expiring": True}},
        ),
        now=NOW,
    )
    assert result.breakdown["life_event"] == 4
    assert result.breakdown["registration_expiring"] == 3


def test_10plus_images_bonus():
    result = score_listing(
        MockListing(year=2020, images=["a.jpg"] * 12),
        now=NOW,
    )
    assert result.breakdown["image_count"] == 8


def test_verdict_thresholds():
    assert verdict_for_score(85) == "hot"
    assert verdict_for_score(70) == "warm"
    assert verdict_for_score(50) == "monitor"
    assert verdict_for_score(30) == "cold"
    assert verdict_for_score(10) == "reject"
    assert verdict_for_score(None) == "unknown"
    # Threshold constants check
    assert HOT_THRESHOLD == 80
    assert WARM_THRESHOLD == 65
    assert MONITOR_THRESHOLD == 45
    assert COLD_THRESHOLD == 25
