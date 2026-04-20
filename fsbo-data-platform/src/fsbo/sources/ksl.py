"""KSL Classifieds source.

KSL (cars.ksl.com) is the dominant FSBO marketplace across Utah, Idaho,
Wyoming, and parts of Nevada. ~95% FSBO mix and 100K+ active vehicle
listings. Their web search results embed JSON-LD `Vehicle` blocks on
each result card, so this is cheap to parse without Playwright.

ToS posture is moderate — public listings with no login required. We
apply a polite rate limit via the shared throttle() helper. Still route
through a residential proxy when PROXY_URL is set for production volume.
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

_SEARCH_URL = "https://cars.ksl.com/search/make/{make}"
_BASE_SEARCH = "https://cars.ksl.com/search"

_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")


class KSLClassifiedsSource(Source):
    name = "ksl"

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
        year_min: int | None = None,
        year_max: int | None = None,
        zip_code: str | None = None,
        limit: int = 30,
        **_: Any,
    ) -> AsyncIterator[NormalizedListing]:
        params: dict[str, str] = {"sellerType": "Private"}
        if make:
            params["make"] = make
        if model:
            params["model"] = model
        if year_min is not None:
            params["yearFrom"] = str(year_min)
        if year_max is not None:
            params["yearTo"] = str(year_max)
        if zip_code:
            params["zip"] = zip_code

        await throttle("ksl")
        try:
            resp = await self._client.get(_BASE_SEARCH, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("ksl.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        yielded = 0
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            blocks = payload if isinstance(payload, list) else [payload]
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("@type") not in ("Vehicle", "Product", "Car"):
                    continue
                listing = self._parse(block)
                if listing:
                    yielded += 1
                    yield listing
                    if yielded >= limit:
                        return

    def _parse(self, block: dict[str, Any]) -> NormalizedListing | None:
        url = block.get("url") or ""
        if not url:
            return None
        external_id = url.rsplit("/", 1)[-1].split("?")[0] or url

        title = block.get("name")
        description = block.get("description")
        year = block.get("vehicleModelDate")
        try:
            year_int: int | None = int(year) if year else None
        except (ValueError, TypeError):
            year_int = None
        if not year_int and title:
            m = _YEAR_RE.search(title)
            if m:
                year_int = int(m.group(1))

        manufacturer = block.get("manufacturer")
        make_name = (
            manufacturer.get("name") if isinstance(manufacturer, dict) else manufacturer
        )
        model_name = block.get("model")

        mileage_raw = block.get("mileageFromOdometer") or {}
        mileage: int | None = None
        if isinstance(mileage_raw, dict):
            value = mileage_raw.get("value")
            if value is not None:
                try:
                    mileage = int(value)
                except (ValueError, TypeError):
                    mileage = None

        offers = block.get("offers") or {}
        price: float | None = None
        if isinstance(offers, dict):
            raw_price = offers.get("price")
            if raw_price is not None:
                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    price = None

        vin = block.get("vehicleIdentificationNumber")

        images: list[str] = []
        image = block.get("image")
        if isinstance(image, str):
            images = [image]
        elif isinstance(image, list):
            images = [i for i in image if isinstance(i, str)]

        return NormalizedListing(
            source=self.name,
            external_id=str(external_id),
            url=url,
            title=title,
            description=description,
            year=year_int,
            make=make_name if isinstance(make_name, str) else None,
            model=model_name if isinstance(model_name, str) else None,
            mileage=mileage,
            price=price,
            vin=vin if isinstance(vin, str) else None,
            images=images,
            raw={"jsonld": block},
        )

    async def aclose(self) -> None:
        await self._client.aclose()
