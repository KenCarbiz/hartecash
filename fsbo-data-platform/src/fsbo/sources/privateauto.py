"""PrivateAuto source.

PrivateAuto (privateauto.com) is a 100% FSBO-only marketplace launched
in 2022 with built-in escrow + e-sign + DMV workflow. Fastest-growing
FSBO-only platform as of 2026 with ~20K active listings.

Listings are publicly accessible with embedded Next.js data. We parse the
`__NEXT_DATA__` script block (Next.js standard for server-rendered
content) which contains the full listing JSON before hydration.

Legal posture: public listings, no login required to view. Polite rate
limited. Production volume should still route through a proxy.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
from bs4 import BeautifulSoup

from fsbo.config import settings
from fsbo.logging import get_logger
from fsbo.sources.base import NormalizedListing, Source
from fsbo.sources.rate_limit import throttle

log = get_logger(__name__)

_SEARCH_URL = "https://privateauto.com/cars-for-sale"

_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")


class PrivateAutoSource(Source):
    name = "privateauto"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        kwargs: dict[str, Any] = {"timeout": 30.0, "follow_redirects": True}
        if settings.proxy_url:
            kwargs["proxy"] = settings.proxy_url
        self._client = client or httpx.AsyncClient(
            **kwargs,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    async def fetch(
        self,
        make: str | None = None,
        model: str | None = None,
        zip_code: str | None = None,
        radius_miles: int = 100,
        limit: int = 30,
        **_: Any,
    ) -> AsyncIterator[NormalizedListing]:
        params: dict[str, str] = {}
        if make:
            params["make"] = make
        if model:
            params["model"] = model
        if zip_code:
            params["zip"] = zip_code
            params["radius"] = str(radius_miles)

        await throttle("privateauto")
        try:
            resp = await self._client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("privateauto.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        data_script = soup.find("script", id="__NEXT_DATA__")
        if not data_script or not data_script.string:
            log.warning("privateauto.no_next_data")
            return

        try:
            payload = json.loads(data_script.string)
        except (json.JSONDecodeError, TypeError):
            return

        # Walk the payload looking for an array of listing-like objects.
        yielded = 0
        for listing_obj in _iter_listings(payload):
            parsed = self._parse(listing_obj)
            if parsed:
                yielded += 1
                yield parsed
                if yielded >= limit:
                    return

    def _parse(self, item: dict[str, Any]) -> NormalizedListing | None:
        external_id = str(
            item.get("id")
            or item.get("_id")
            or item.get("listingId")
            or item.get("slug")
            or ""
        )
        if not external_id:
            return None

        slug = item.get("slug") or external_id
        url = f"https://privateauto.com/listings/{slug}"

        title = item.get("title") or item.get("headline")
        description = item.get("description") or item.get("details")

        year = _safe_int(item.get("year"))
        make = _safe_str(item.get("make"))
        model = _safe_str(item.get("model"))
        trim = _safe_str(item.get("trim"))
        mileage = _safe_int(item.get("mileage") or item.get("odometer"))
        price = _safe_float(item.get("price") or item.get("askingPrice"))
        vin = _safe_str(item.get("vin"))

        if not year and title:
            m = _YEAR_RE.search(title)
            if m:
                year = int(m.group(1))

        location = item.get("location") or {}
        city = _safe_str(location.get("city") if isinstance(location, dict) else None)
        state = _safe_str(location.get("state") if isinstance(location, dict) else None)
        zip_code = _safe_str(location.get("zip") if isinstance(location, dict) else None)

        images_raw = item.get("images") or item.get("photos") or []
        images: list[str] = []
        if isinstance(images_raw, list):
            for img in images_raw[:8]:
                if isinstance(img, str):
                    images.append(img)
                elif isinstance(img, dict):
                    url_val = img.get("url") or img.get("src")
                    if isinstance(url_val, str):
                        images.append(url_val)

        return NormalizedListing(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            description=description,
            year=year,
            make=make,
            model=model,
            trim=trim,
            mileage=mileage,
            price=price,
            vin=vin,
            city=city,
            state=state,
            zip_code=zip_code,
            images=images,
            raw={"next_data": item},
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _iter_listings(obj: Any, depth: int = 0) -> Any:
    """Recursively walk a Next.js __NEXT_DATA__ payload looking for arrays
    that look like listings. Heuristic: arrays of dicts that contain
    'price' and ('make' or 'year')."""
    if depth > 8:
        return
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            first = obj[0]
            if "price" in first and ("make" in first or "year" in first or "slug" in first):
                yield from obj
                return
        for item in obj:
            yield from _iter_listings(item, depth + 1)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_listings(v, depth + 1)


def _safe_str(val: Any) -> str | None:
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
