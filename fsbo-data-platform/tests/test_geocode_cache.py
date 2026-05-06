"""Geocoder cache + Census fallback.

The 20-ZIP hardcoded shim still works (hot-path bypass). Beyond
that, the lookup hits the zip_geocodes cache table; on cache miss
it falls back to Census Geocoder over httpx (mocked here).
"""

import httpx
import pytest

from fsbo.enrichment import geocode as geomod
from fsbo.enrichment.geocode import (
    GeoPoint,
    geocode,
    geocode_cached_only,
)
from fsbo.models import ZipGeocode


def test_fallback_zip_returns_without_db_or_network(monkeypatch):
    # Tampa is in _FALLBACK_ZIPS. No DB, no network.
    monkeypatch.setattr(geomod, "_from_census", lambda z, **kw: pytest.fail("network"))
    p = geocode("33607")
    assert p is not None
    assert round(p.lat, 2) == 27.97


def test_invalid_zip_returns_none():
    # Both short-circuit in _normalize_zip before any DB / network hit.
    assert geocode("not-a-zip") is None
    assert geocode(None) is None
    assert geocode("12") is None  # too short
    assert geocode("ABCDE") is None  # not numeric


def test_cache_hit_skips_network(db_session, monkeypatch):
    db_session.add(
        ZipGeocode(zip_code="11111", lat=42.0, lon=-71.0, source="seed")
    )
    db_session.flush()
    called = {"n": 0}

    def boom(z, **kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(geomod, "_from_census", boom)
    p = geocode("11111", db=db_session)
    assert p is not None
    assert p.lat == 42.0
    assert called["n"] == 0


def test_census_miss_persists_to_cache(db_session, monkeypatch):
    monkeypatch.setattr(
        geomod,
        "_from_census",
        lambda z, **kw: GeoPoint(lat=12.34, lon=-56.78),
    )
    p = geocode("22222", db=db_session)
    assert p is not None
    row = db_session.get(ZipGeocode, "22222")
    assert row is not None
    assert row.source == "census"
    assert round(row.lat, 2) == 12.34


def test_use_census_false_returns_none_on_miss(db_session, monkeypatch):
    monkeypatch.setattr(
        geomod, "_from_census", lambda z, **kw: pytest.fail("should not call")
    )
    p = geocode("33333", db=db_session, use_census=False)
    assert p is None


def test_geocode_cached_only_never_calls_network(db_session, monkeypatch):
    monkeypatch.setattr(
        geomod, "_from_census", lambda z, **kw: pytest.fail("should not call")
    )
    # Hardcoded fallback hit
    assert geocode_cached_only("33607") is not None
    # Cached row hit
    db_session.add(ZipGeocode(zip_code="44444", lat=1.0, lon=2.0, source="seed"))
    db_session.flush()
    assert geocode_cached_only("44444", db=db_session) is not None
    # Truly unknown -> None, no network
    assert geocode_cached_only("99999", db=db_session) is None


def test_census_request_shape(monkeypatch):
    """Confirm we hit the documented Census /onelineaddress endpoint
    with the right benchmark + format params."""
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["params"] = dict(req.url.params)
        return httpx.Response(
            200,
            json={
                "result": {
                    "addressMatches": [
                        {"coordinates": {"x": -82.5, "y": 28.0}}
                    ]
                }
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return original_client(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    p = geomod._from_census("33607")
    assert p is not None
    assert "geocoding.geo.census.gov" in captured["url"]
    assert captured["params"]["benchmark"] == "Public_AR_Current"
    assert captured["params"]["format"] == "json"
