"""OfferUp source.

OfferUp is a peer-to-peer marketplace with a car-specific category. Unlike
Craigslist, their search pages are JavaScript-rendered, but individual
item detail pages embed structured JSON-LD that we can parse cheaply.

IMPORTANT: OfferUp's Terms of Service restricts automated scraping. This
adapter is written to the same interface as the other sources but is
disabled by default (set PROXY_URL or a proper deal with OfferUp before
enabling). It's here so the pipeline understands the shape; your legal
team must greenlight usage before it sees real traffic.

The implementation below parses JSON-LD `Product` blocks if the HTML we
fetch contains them. Without a browser context (Playwright), search
pages usually return a skeleton. Item detail URLs — once a dealer
browses them via the Chrome extension — DO include JSON-LD.
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

log = get_logger(__name__)

_SEARCH_URL = "https://offerup.com/search"

_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")


class OfferUpSource(Source):
    name = "offerup"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        transport_kwargs: dict[str, Any] = {"timeout": 30.0, "follow_redirects": True}
        if settings.proxy_url:
            transport_kwargs["proxy"] = settings.proxy_url
        self._client = client or httpx.AsyncClient(
            **transport_kwargs,
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
        q: str | None = None,
        zip_code: str | None = None,
        radius_miles: int = 100,
        limit: int = 30,
        **_: Any,
    ) -> AsyncIterator[NormalizedListing]:
        if not settings.proxy_url:
            log.warning(
                "offerup.no_proxy_configured",
                message=(
                    "OfferUp source requires PROXY_URL for production scraping. "
                    "Returning no results. Configure a residential proxy and ensure "
                    "legal review has cleared OfferUp scraping before enabling."
                ),
            )
            return

        params: dict[str, str] = {"category_id": "18"}  # 18 = Cars & Trucks on OfferUp
        if q:
            params["q"] = q
        if zip_code:
            params["lon"] = ""
            params["lat"] = ""
            params["loc"] = zip_code
            params["radius"] = str(radius_miles)

        try:
            resp = await self._client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("offerup.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        yielded = 0
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            # JSON-LD blocks can be a single object or a list.
            blocks = payload if isinstance(payload, list) else [payload]
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("@type") != "Product":
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
        image = block.get("image")
        images: list[str] = []
        if isinstance(image, str):
            images = [image]
        elif isinstance(image, list):
            images = [i for i in image if isinstance(i, str)]

        price: float | None = None
        offers = block.get("offers")
        if isinstance(offers, dict):
            raw_price = offers.get("price")
            if raw_price is not None:
                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    price = None

        year = None
        if title:
            m = _YEAR_RE.search(title)
            if m:
                year = int(m.group(1))

        return NormalizedListing(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            description=description,
            year=year,
            price=price,
            images=images,
            raw={"jsonld": block},
        )

    async def aclose(self) -> None:
        await self._client.aclose()
