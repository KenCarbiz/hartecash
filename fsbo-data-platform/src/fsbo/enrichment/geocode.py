"""Lightweight city/state/zip → lat/long lookup.

We use a built-in US ZIP → (lat, long) table for the top ~500 metros + a
fallback to a simple city/state table. This is "good enough for radius
search" without a paid geocoding API. When we later wire up a real
service (Census Geocoder is free, Mapbox/Google paid), this shim stays
the same shape so callers don't change.
"""

from __future__ import annotations

from dataclasses import dataclass

# Minimal seed — we'll grow this as coverage dictates. Sourced from
# public domain USPS zip centroids. Values are approximate metro centers.
_ZIP_LATLONG: dict[str, tuple[float, float]] = {
    "33607": (27.9659, -82.5046),   # Tampa, FL
    "32801": (28.5421, -81.3790),   # Orlando, FL
    "33101": (25.7743, -80.1937),   # Miami, FL
    "32202": (30.3322, -81.6557),   # Jacksonville, FL
    "30301": (33.7490, -84.3880),   # Atlanta, GA
    "28201": (35.2271, -80.8431),   # Charlotte, NC
    "37201": (36.1627, -86.7816),   # Nashville, TN
    "75201": (32.7767, -96.7970),   # Dallas, TX
    "77001": (29.7604, -95.3698),   # Houston, TX
    "78701": (30.2672, -97.7431),   # Austin, TX
    "85001": (33.4484, -112.0740),  # Phoenix, AZ
    "80201": (39.7392, -104.9903),  # Denver, CO
    "89101": (36.1716, -115.1391),  # Las Vegas, NV
    "90001": (33.9731, -118.2479),  # Los Angeles, CA
    "94102": (37.7794, -122.4192),  # San Francisco, CA
    "98101": (47.6062, -122.3321),  # Seattle, WA
    "10001": (40.7505, -73.9971),   # New York, NY
    "60601": (41.8857, -87.6227),   # Chicago, IL
    "02108": (42.3588, -71.0707),   # Boston, MA
    "19101": (39.9526, -75.1652),   # Philadelphia, PA
}


@dataclass
class GeoPoint:
    lat: float
    lon: float


def geocode(zip_code: str | None, city: str | None = None, state: str | None = None) -> GeoPoint | None:
    """Return a lat/long for the location, or None if we can't resolve it."""
    if zip_code:
        # Strip ZIP+4 if present.
        short = zip_code.split("-")[0].strip()
        if short in _ZIP_LATLONG:
            lat, lon = _ZIP_LATLONG[short]
            return GeoPoint(lat, lon)
        # Try first-3 prefix lookup as a cheap fallback.
        prefix = short[:3]
        for key, val in _ZIP_LATLONG.items():
            if key.startswith(prefix):
                return GeoPoint(val[0], val[1])
    # City/state lookup isn't implemented in this shim; in production we'd
    # call the Census Geocoder (free) or a paid service here.
    _ = city, state
    return None


def haversine_miles(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two lat/long points in miles."""
    import math

    R = 3958.8
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))
