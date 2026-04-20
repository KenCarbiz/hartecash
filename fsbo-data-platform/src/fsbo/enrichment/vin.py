"""NHTSA vPIC VIN decoder.

Free, no API key, no rate limit in practice. Enriches year/make/model/trim
from a VIN when the source listing didn't provide them.

Docs: https://vpic.nhtsa.dot.gov/api/
Endpoint: DecodeVinValues returns a flat dict — easiest to consume.
"""

from dataclasses import dataclass

import httpx

from fsbo.logging import get_logger

log = get_logger(__name__)

_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}"


@dataclass
class DecodedVin:
    vin: str
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    body_class: str | None = None
    error_code: str | None = None
    error_text: str | None = None


async def decode_vin(vin: str, client: httpx.AsyncClient | None = None) -> DecodedVin | None:
    """Decode a single VIN. Returns None on network failure or invalid VIN format."""
    vin = (vin or "").strip().upper()
    if len(vin) != 17:
        return None

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=15.0)
    try:
        resp = await client.get(_URL.format(vin=vin), params={"format": "json"})
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as e:
        log.warning("vin_decode.http_error", vin=vin, error=str(e))
        return None
    finally:
        if owns_client:
            await client.aclose()

    results = payload.get("Results") or []
    if not results:
        return None
    row = results[0]

    def _s(key: str) -> str | None:
        v = row.get(key)
        return v.strip() if isinstance(v, str) and v.strip() else None

    year_str = _s("ModelYear")
    year: int | None = None
    if year_str:
        try:
            year = int(year_str)
        except ValueError:
            year = None

    return DecodedVin(
        vin=vin,
        year=year,
        make=_s("Make"),
        model=_s("Model"),
        trim=_s("Trim"),
        body_class=_s("BodyClass"),
        error_code=_s("ErrorCode"),
        error_text=_s("ErrorText"),
    )
