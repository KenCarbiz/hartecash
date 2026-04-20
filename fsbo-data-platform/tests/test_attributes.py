from fsbo.enrichment.attributes import extract
from fsbo.sources.base import NormalizedListing


def _listing(desc: str) -> NormalizedListing:
    return NormalizedListing(source="test", external_id="1", url="http://x", description=desc)


def test_title_type_salvage():
    a = extract(_listing("2015 Civic salvage title, needs work"))
    assert a.title_type == "salvage"


def test_title_type_clean():
    a = extract(_listing("2018 Accord clean title, one owner"))
    assert a.title_type == "clean"


def test_transmission_manual():
    a = extract(_listing("6-speed manual, fun to drive"))
    assert a.transmission == "manual"


def test_drivetrain_4wd():
    a = extract(_listing("4x4 off-road ready, clean title"))
    assert a.drivetrain == "4wd"


def test_features_multiple():
    a = extract(
        _listing(
            "Loaded with leather seats, sunroof, navigation, tow package, heated seats, Bluetooth, Apple CarPlay"
        )
    )
    assert set(a.features) >= {
        "leather",
        "sunroof",
        "navigation",
        "tow_package",
        "heated_seats",
        "bluetooth",
        "apple_carplay",
    }


def test_owner_count_one():
    a = extract(_listing("one owner, non-smoker, garage kept"))
    assert a.owner_count == 1


def test_service_records():
    a = extract(_listing("All service records available, maintained at dealer"))
    assert a.has_service_records is True


def test_accident_mentioned():
    a = extract(_listing("Clean history, no accidents"))
    assert a.accident_mentioned is True


def test_negotiable_obo():
    a = extract(_listing("$15,000 OBO, cash only"))
    assert a.negotiable is True


def test_firm_price():
    a = extract(_listing("$15,000 firm, no lowballs"))
    assert a.negotiable is False
