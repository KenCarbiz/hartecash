"""Bring a Trailer source.

BaT (bringatrailer.com) is an enthusiast-auction marketplace, 80%+ FSBO,
collector + modern-classic cars. Runs ~500 auctions per week. Each
auction page has rich JSON-LD describing the vehicle.

Different use-case from mass-market FSBO: BaT sellers are often enthusiasts
with well-documented cars. Values skew higher. For an AutoCurb dealer
doing specialty / enthusiast acquisition, this is pure signal.

Listing URL pattern: bringatrailer.com/listing/<slug>/
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

_AUCTIONS_URL = "https://bringatrailer.com/auctions/"
_YEAR_RE = re.compile(r"\b(19\d{2}|20[0-3]\d)\b")


class BringATrailerSource(Source):
    name = "bring_a_trailer"

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

    async def fetch(self, limit: int = 30, **_: Any) -> AsyncIterator[NormalizedListing]:
        await throttle("bring_a_trailer")
        try:
            resp = await self._client.get(_AUCTIONS_URL)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("bat.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        # BaT's auction tiles link to the detail page; collect unique URLs
        # then parse JSON-LD from each. Cap at `limit` detail fetches.
        seen: set[str] = set()
        links: list[str] = []
        for a in soup.select('a[href*="/listing/"]'):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            if "/listing/" not in href:
                continue
            seen.add(href)
            links.append(href if href.startswith("http") else f"https://bringatrailer.com{href}")
            if len(links) >= limit:
                break

        yielded = 0
        for url in links:
            parsed = await self._fetch_detail(url)
            if parsed:
                yielded += 1
                yield parsed
                if yielded >= limit:
                    return

    async def _fetch_detail(self, url: str) -> NormalizedListing | None:
        await throttle("bring_a_trailer")
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            blocks = payload if isinstance(payload, list) else [payload]
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("@type") not in ("Product", "Vehicle", "Car"):
                    continue
                return self._parse(block, url)
        return None

    def _parse(self, block: dict[str, Any], url: str) -> NormalizedListing | None:
        title = block.get("name")
        description = block.get("description")
        external_id = url.rstrip("/").rsplit("/", 1)[-1]

        year: int | None = None
        if title:
            m = _YEAR_RE.search(title)
            if m:
                year = int(m.group(1))

        manufacturer = block.get("manufacturer")
        make = (
            manufacturer.get("name") if isinstance(manufacturer, dict) else manufacturer
        )
        model = block.get("model")

        offers = block.get("offers") or {}
        price: float | None = None
        if isinstance(offers, dict):
            raw = offers.get("highPrice") or offers.get("price")
            if raw is not None:
                try:
                    price = float(raw)
                except (TypeError, ValueError):
                    price = None

        images: list[str] = []
        image = block.get("image")
        if isinstance(image, str):
            images = [image]
        elif isinstance(image, list):
            images = [i for i in image if isinstance(i, str)][:8]

        return NormalizedListing(
            source=self.name,
            external_id=external_id,
            url=url,
            title=title,
            description=description,
            year=year,
            make=make if isinstance(make, str) else None,
            model=model if isinstance(model, str) else None,
            price=price,
            images=images,
            raw={"jsonld": block},
        )

    async def aclose(self) -> None:
        await self._client.aclose()
