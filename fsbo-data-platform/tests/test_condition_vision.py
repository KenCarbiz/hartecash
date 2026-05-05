"""Condition vision: pin the JSON parser + value-space clamping.

We don't test the actual Anthropic call (that's stubbed by `no api key`
shortcut). We test that the dataclass + as_dict() shape matches what
the dashboard expects.
"""

from fsbo.enrichment.condition_vision import ConditionAssessment


def test_default_assessment_is_unknown_everywhere():
    a = ConditionAssessment()
    d = a.as_dict()
    assert d["overall"] == "unknown"
    assert d["body_damage"] == "unknown"
    assert d["paint"] == "unknown"
    assert d["interior"] == "unknown"
    assert d["tires"] == "unknown"
    assert d["notes"] == ""
    assert d["flags"] == []
    assert d["checked_images"] == 0
    assert d["source_image"] is None


def test_as_dict_round_trip():
    a = ConditionAssessment(
        overall="good",
        body_damage="cosmetic",
        paint="fair",
        interior="good",
        tires="excellent",
        notes="Front bumper has a fresh scrape on the driver side.",
        flags=["fresh_scrape", "fading_paint"],
        checked_images=3,
        source_image="https://example.com/photo1.jpg",
    )
    d = a.as_dict()
    assert d["overall"] == "good"
    assert d["body_damage"] == "cosmetic"
    assert "fresh_scrape" in d["flags"]
    assert d["checked_images"] == 3
