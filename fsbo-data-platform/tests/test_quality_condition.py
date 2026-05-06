"""Lead quality scorer pulls in AI vision condition assessment.

Before this fix the condition_vision result lived on listing.condition
but never fed lead_quality_score. A pretty-looking listing whose photos
showed a wrecked truck would still score "hot."
"""

from types import SimpleNamespace

from fsbo.enrichment.quality import score_listing


def _listing(**condition):
    return SimpleNamespace(
        title="2018 Ford F-150 XLT",
        description="One owner, clean title.",
        year=2018,
        make="Ford",
        model="F-150",
        price=22000,
        mileage=80000,
        seller_phone="8135551234",
        raw={"attributes": {}},
        condition=condition,
    )


def test_excellent_condition_lifts_score():
    plain = score_listing(_listing()).score
    excellent = score_listing(
        _listing(checked_images=1, overall="excellent", body_damage="none", flags=[])
    ).score
    assert excellent > plain
    assert excellent - plain >= 8


def test_heavy_body_damage_drops_score_and_flags_reason():
    res = score_listing(
        _listing(
            checked_images=1,
            overall="fair",
            body_damage="heavy",
            flags=["misaligned_panel"],
        )
    )
    assert res.score < 50
    assert res.auto_hide_reason and "body damage" in res.auto_hide_reason


def test_unscanned_listing_no_condition_signal():
    """checked_images == 0 -> no condition contribution to breakdown."""
    res = score_listing(_listing(checked_images=0))
    assert "condition_overall" not in res.breakdown
    assert "condition_body_damage" not in res.breakdown


def test_specific_flags_compound_penalty():
    res = score_listing(
        _listing(
            checked_images=2,
            overall="good",
            body_damage="cosmetic",
            flags=["rust", "cracked_windshield", "fresh_scrape"],
        )
    )
    # 3 bad tags -> -9 from flags
    assert res.breakdown.get("condition_flags") == -9
