from fsbo.enrichment.dealer_signals import assess, extract_signals
from fsbo.sources.base import NormalizedListing


def _listing(**kwargs) -> NormalizedListing:
    return NormalizedListing(source="test", external_id="1", url="http://x", **kwargs)


def test_obvious_dealer_flagged():
    listing = _listing(
        title="2020 Ford F-150 — Financing Available",
        description="We finance everyone! Trade-ins welcome. Call our sales team. More inventory on our lot.",
    )
    result = assess(listing)
    assert result.likelihood > 0.9


def test_spanish_dealer_flagged():
    listing = _listing(
        title="2019 Toyota Camry",
        description="Financiamiento fácil. Sin crédito OK. Tenemos más carros en nuestro lote. Aceptamos cambios.",
    )
    result = assess(listing)
    assert result.likelihood > 0.8


def test_genuine_private_seller_not_flagged():
    listing = _listing(
        title="2018 Honda Accord — one owner",
        description="Clean title, non-smoker, service records, text for pics.",
    )
    result = assess(listing)
    assert result.likelihood < 0.2


def test_scam_score_wire_transfer():
    listing = _listing(
        title="2015 BMW",
        description="Shipping only. Western Union payment. Deployed military.",
    )
    result = assess(listing)
    assert result.scam_score >= 0.6


def test_phone_cross_listing_boosts_dealer_likelihood():
    listing = _listing(
        title="2020 Ford Mustang",
        description="Great car, clean title.",
    )
    no_extras = assess(listing).likelihood
    with_extras = assess(
        listing,
        extra={
            "phone_on_3plus_listings_30d": True,
            "phone_on_5plus_listings_90d": True,
        },
    ).likelihood
    assert with_extras > no_extras


def test_all_caps_signal():
    listing = _listing(
        title="MUST SEE! CLEAN TITLE!",
        description="THIS IS A GREAT DEAL ON THIS USED CAR YOU WILL LOVE IT",
    )
    sigs = extract_signals(listing)
    assert sigs.get("all_caps_ratio_high")
