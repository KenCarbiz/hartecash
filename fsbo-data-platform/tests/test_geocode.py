from fsbo.enrichment import geocode as geomod
from fsbo.enrichment.geocode import GeoPoint, geocode, haversine_miles


def test_known_zip_resolves():
    p = geocode("33607")
    assert p is not None
    assert 27 < p.lat < 29 and -83 < p.lon < -82


def test_unknown_zip_with_no_cache_and_no_census(db_session, monkeypatch):
    """A ZIP that isn't in the hot-path fallback + isn't cached + Census
    fails should return None, not crash."""
    monkeypatch.setattr(geomod, "_from_census", lambda z, **kw: None)
    p = geocode("99999", db=db_session)
    assert p is None


def test_zip_plus_4_stripped():
    # +4 strips to 33607 which IS in the hot-path fallback.
    p = geocode("33607-1234")
    assert p is not None


def test_haversine_approx_sf_la():
    sf = GeoPoint(37.7749, -122.4194)
    la = GeoPoint(34.0522, -118.2437)
    d = haversine_miles(sf, la)
    # Real-world distance is ~347 miles
    assert 340 < d < 360


def test_haversine_zero_distance():
    p = GeoPoint(33.0, -96.0)
    assert haversine_miles(p, p) < 0.001
