from fsbo.enrichment.classifier import classify_heuristic
from fsbo.enrichment.dedup import compute_dedup_key
from fsbo.models import Classification
from fsbo.sources.base import NormalizedListing


def _listing(**kwargs) -> NormalizedListing:
    return NormalizedListing(source="test", external_id="1", url="http://x", **kwargs)


def test_heuristic_flags_dealer():
    result = classify_heuristic(
        _listing(title="Clean 2020 truck", description="Financing available. Trade-ins welcome. We finance.")
    )
    assert result is not None
    assert result.label == Classification.DEALER.value


def test_heuristic_flags_scam():
    result = classify_heuristic(
        _listing(title="2015 BMW", description="Shipping only, paying via Western Union")
    )
    assert result is not None
    assert result.label == Classification.SCAM.value


def test_heuristic_passes_genuine_private_seller():
    result = classify_heuristic(
        _listing(
            title="2018 Honda Accord 85k miles",
            description="Selling my daily driver. Clean title, one owner. Text for details.",
        )
    )
    assert result is None  # heuristics can't confidently decide -> LLM


def test_dedup_by_vin():
    key = compute_dedup_key(_listing(vin="1HGBH41JXMN109186"))
    assert key == "vin:1HGBH41JXMN109186"


def test_dedup_by_phone_and_vehicle():
    key = compute_dedup_key(
        _listing(seller_phone="(813) 555-1234", year=2018, make="Ford", model="F-150")
    )
    assert key is not None and key.startswith("phv:")


def test_dedup_no_signal():
    assert compute_dedup_key(_listing(title="some car")) is None
