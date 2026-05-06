"""ZIP / city / state -> lat/long with persistent cache + Census fallback.

Lookup chain (fastest to slowest):

  1. _FALLBACK_ZIPS — built-in 20-metro hot-path. Zero network, zero
     DB. Covers most dev/CI usage and the radius search center
     queries we know about at deploy time.
  2. zip_geocodes table — persistent cache. Every ZIP we've ever
     looked up lives here forever (the answer never changes).
  3. Census Geocoder API — https://geocoding.geo.census.gov, free,
     no API key. Result is persisted to zip_geocodes so the next
     lookup hits step 2.

The radius search at /listings hits this for the center ZIP +
potentially thousands of candidate ZIPs. To bound the worst case
(fresh deploy, no cache, no fallback hit) the candidate path uses
`geocode_cached_only(...)` which skips the Census call — listings
without a cached ZIP just don't appear in radius results until
the cache is warmed (operationally fine; degrades gracefully).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from fsbo.db import SessionLocal
from fsbo.models import ZipGeocode

logger = logging.getLogger(__name__)


# Hot-path bypass — top metros, public-domain USPS zip centroids.
_FALLBACK_ZIPS: dict[str, tuple[float, float]] = {
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

CENSUS_URL = (
    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
)


@dataclass
class GeoPoint:
    lat: float
    lon: float


def _normalize_zip(zip_code: str | None) -> str | None:
    if not zip_code:
        return None
    short = zip_code.split("-")[0].strip()
    if not short.isdigit() or len(short) != 5:
        return None
    return short


def _from_fallback(z: str) -> GeoPoint | None:
    if z in _FALLBACK_ZIPS:
        lat, lon = _FALLBACK_ZIPS[z]
        return GeoPoint(lat, lon)
    return None


def _from_cache(db: Session, z: str) -> GeoPoint | None:
    row = db.get(ZipGeocode, z)
    if row is None:
        return None
    return GeoPoint(row.lat, row.lon)


def _persist(db: Session, z: str, lat: float, lon: float, source: str) -> None:
    if db.get(ZipGeocode, z) is not None:
        return
    db.add(ZipGeocode(zip_code=z, lat=lat, lon=lon, source=source))
    try:
        db.flush()
    except Exception:  # noqa: BLE001
        # Race / unique-violation — another worker beat us. Fine.
        db.rollback()


def _from_census(z: str, *, timeout: float = 3.0) -> GeoPoint | None:
    """Hit Census Geocoder /onelineaddress for the bare ZIP. Free,
    no API key. Returns None on timeout / parse error / no match."""
    params = {
        "address": z,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(CENSUS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.debug("census.fetch_failed zip=%s err=%s", z, e)
        return None

    matches = (data.get("result") or {}).get("addressMatches") or []
    if not matches:
        return None
    coords = (matches[0] or {}).get("coordinates") or {}
    try:
        lat = float(coords["y"])
        lon = float(coords["x"])
    except (KeyError, TypeError, ValueError):
        return None
    return GeoPoint(lat=lat, lon=lon)


def geocode_cached_only(
    zip_code: str | None,
    *,
    db: Session | None = None,
) -> GeoPoint | None:
    """Lookup that NEVER hits the network. Use this in hot loops
    (radius search candidate iteration) so a 5000-row scan against a
    cold cache doesn't fan out 5000 Census calls."""
    z = _normalize_zip(zip_code)
    if not z:
        return None
    fallback = _from_fallback(z)
    if fallback is not None:
        return fallback
    if db is not None:
        return _from_cache(db, z)
    # Open a short-lived session for sync callers that don't pass one.
    with SessionLocal() as scoped:
        return _from_cache(scoped, z)


def geocode(
    zip_code: str | None,
    city: str | None = None,
    state: str | None = None,
    *,
    db: Session | None = None,
    use_census: bool = True,
) -> GeoPoint | None:
    """Resolve a ZIP -> GeoPoint. Cache-first, network-fallback.

    Backward-compatible signature with the old shim — radius search
    + extension ingest both call this without changes. The `db` arg
    lets callers reuse their existing Session; without it, we open
    a short-lived session for the cache lookup."""
    z = _normalize_zip(zip_code)
    if not z:
        # City/state-only lookup isn't implemented — Census's address
        # endpoint accepts city+state but we don't have a use case yet.
        _ = city, state
        return None

    fallback = _from_fallback(z)
    if fallback is not None:
        return fallback

    # DB cache
    if db is not None:
        cached = _from_cache(db, z)
        if cached is not None:
            return cached
    else:
        with SessionLocal() as scoped:
            cached = _from_cache(scoped, z)
        if cached is not None:
            return cached

    if not use_census:
        return None

    # Census fallback. Persist on success.
    point = _from_census(z)
    if point is None:
        return None
    if db is not None:
        _persist(db, z, point.lat, point.lon, source="census")
    else:
        with SessionLocal() as scoped:
            _persist(scoped, z, point.lat, point.lon, source="census")
            scoped.commit()
    return point


def haversine_miles(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two lat/long points in miles."""
    R = 3958.8
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(h))
