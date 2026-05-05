"""Plate-vision regex/validation guards.

The model-call path is integration-tested elsewhere; this file pins the
local validator that filters obviously-bogus extractions ("PLATE",
"NONE", or strings that don't match a US plate shape).
"""

from fsbo.enrichment.plate_vision import _looks_valid_plate


def test_accepts_normal_plates():
    assert _looks_valid_plate("ABC1234")
    assert _looks_valid_plate("7GTF123")
    assert _looks_valid_plate("ABC 1234")
    assert _looks_valid_plate("ABC-1234")


def test_rejects_known_garbage():
    assert not _looks_valid_plate("PLATE")
    assert not _looks_valid_plate("NONE")
    assert not _looks_valid_plate("FORD")


def test_rejects_too_short_or_long():
    assert not _looks_valid_plate("AB")
    assert not _looks_valid_plate("ABCDEFGHIJK1234")


def test_normalizes_case_via_caller():
    """Validator expects upper-case input; the caller upper-cases first."""
    assert _looks_valid_plate("ABC1234".upper())
