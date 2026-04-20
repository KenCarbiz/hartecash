from fsbo.enrichment.geocode import GeoPoint, geocode, haversine_miles


def test_known_zip_resolves():
    p = geocode("33607")
    assert p is not None
    assert 27 < p.lat < 29 and -83 < p.lon < -82


def test_unknown_zip_falls_back_to_prefix():
    # 33612 isn't in the table, but 336xx prefix matches Tampa-area zips.
    p = geocode("33612")
    assert p is not None


def test_unknown_completely():
    p = geocode("99999")
    assert p is None


def test_zip_plus_4_stripped():
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
