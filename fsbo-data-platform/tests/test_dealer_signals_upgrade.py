from fsbo.enrichment.dealer_signals import assess
from fsbo.sources.base import NormalizedListing


def _l(**kw):
    return NormalizedListing(source="t", external_id="x", url="http://x", **kw)


def test_crypto_scam_high_confidence():
    r = assess(
        _l(title="2018 BMW", description="Payment via bitcoin or USDT only. Shipping only.")
    )
    assert r.scam_score >= 0.85


def test_zelle_alone_is_soft():
    # Single soft signal shouldn't cross 0.7
    r = assess(_l(title="2018 Honda", description="Zelle payments preferred for faster delivery"))
    assert 0 < r.scam_score < 0.7


def test_hospice_sob_story():
    r = assess(
        _l(description="Inherited from my late father who was in hospice. Estate sale.")
    )
    assert r.scam_score >= 0.45


def test_no_title_in_hand_is_critical():
    r = assess(
        _l(description="Title is in the mail from DMV, I'll mail it to you after payment.")
    )
    # This alone is near-critical
    assert r.scam_score >= 0.85


def test_third_person_self_reference_adds_dealer_weight():
    private = assess(_l(description="I drive this every day. Selling it because I'm moving."))
    dealer_like = assess(
        _l(description="The seller is asking $15,000. The vehicle has new tires. The owner will negotiate.")
    )
    assert dealer_like.likelihood > private.likelihood


def test_stock_phrases_detected():
    r = assess(
        _l(
            description=(
                "Runs and drives great. Clean inside and out. No issues. Must see!"
            )
        )
    )
    assert r.signals.get("has_stock_phrase_run")
    assert r.signals.get("has_stock_phrase_inout")
    assert r.signals.get("has_stock_phrase_no_issues")
    assert r.signals.get("has_stock_phrase_must_see")
