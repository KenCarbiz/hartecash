from datetime import datetime, timezone

from fsbo.enrichment.quality import score_listing


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


NOW = datetime(2026, 4, 20, tzinfo=timezone.utc)


def test_base_score():
    # Provide a few images to avoid the "no images" penalty so base == 50.
    result = score_listing(MockListing(images=["a.jpg", "b.jpg", "c.jpg"]), now=NOW)
    assert result.score == 50
    assert result.breakdown["base"] == 50


def test_below_market_boosts_score():
    listing = MockListing(year=2018, price=18000)
    result = score_listing(
        listing, market={"median": 22000, "sample_size": 10}, now=NOW
    )
    assert result.breakdown["price_vs_market"] > 0
    assert result.score > 50


def test_above_market_penalizes():
    listing = MockListing(year=2018, price=28000)
    result = score_listing(
        listing, market={"median": 22000, "sample_size": 10}, now=NOW
    )
    assert result.breakdown["price_vs_market"] < 0


def test_dealer_risk_kills_score():
    listing = MockListing(year=2018, price=20000)
    result = score_listing(listing, dealer_likelihood=0.85, now=NOW)
    assert result.breakdown["dealer_risk"] == -40


def test_fresh_listing_scores_high():
    listing = MockListing(year=2020)
    result = score_listing(listing, days_on_market=0, now=NOW)
    assert result.breakdown["days_on_market"] == 15


def test_stale_listing_scores_low():
    listing = MockListing(year=2020)
    result = score_listing(listing, days_on_market=90, now=NOW)
    assert result.breakdown["days_on_market"] == -10


def test_ripe_window_gets_small_bonus():
    listing = MockListing(year=2020)
    result = score_listing(listing, days_on_market=14, now=NOW)
    assert result.breakdown["days_on_market"] == 3


def test_price_drops_boost_score():
    listing = MockListing(year=2020)
    result_one = score_listing(listing, price_drops=1, days_on_market=10, now=NOW)
    result_three = score_listing(listing, price_drops=3, days_on_market=10, now=NOW)
    assert result_three.score > result_one.score


def test_curbstoner_phone_penalizes():
    listing = MockListing(year=2020)
    clean = score_listing(listing, phone_listing_count=0, now=NOW)
    curb = score_listing(listing, phone_listing_count=6, now=NOW)
    assert curb.score < clean.score
    assert curb.breakdown["phone_cross_listing"] == -15


def test_valid_vin_adds_trust():
    listing = MockListing(year=2020, vin="1M8GDM9AXKP042788")
    result = score_listing(listing, now=NOW)
    assert result.breakdown["vin_present"] == 5


def test_score_clamped():
    # Stack many negatives; confirm clamp at 0
    listing = MockListing(year=2020, price=50000, images=[])
    result = score_listing(
        listing,
        market={"median": 10000, "sample_size": 10},
        dealer_likelihood=0.9,
        scam_score=0.9,
        phone_listing_count=10,
        days_on_market=200,
        now=NOW,
    )
    assert result.score == 0
