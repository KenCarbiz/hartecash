"""Bookoo (bookoo.com) source — military-base-focused FSBO.

Community marketplace concentrated around military bases (Ft. Bragg,
Camp Lejeune, etc). ~80% FSBO mix with unique PCS-move inventory
(relocating military families sell quickly).

Public HTML, no login, no enforcement history. Listings pages don't
consistently embed JSON-LD so we parse the item tiles via simple
DOM queries.
"""

from __future__ import annotations

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

_SEARCH_URL = "https://bookoo.com/search"
_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")
_PRICE_RE = re.compile(r"\$[\s]?([\d,]+)")


class BookooSource(Source):
    name = "bookoo"

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
        q: str | None = "cars",
        community: str | None = None,
        limit: int = 30,
        **_: Any,
    ) -> AsyncIterator[NormalizedListing]:
        params: dict[str, str] = {"q": q or "cars", "category": "autos"}
        if community:
            params["community"] = community

        await throttle("bookoo")
        try:
            resp = await self._client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("bookoo.fetch_failed", error=str(e))
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        yielded = 0
        # Bookoo listing tiles expose an <a href="/item/..."> with the
        # price and title nearby. Adjust selectors if they restructure.
        for anchor in soup.select('a[href*="/item/"]'):
            href = anchor.get("href", "")
            if not href:
                continue
            url = href if href.startswith("http") else f"https://bookoo.com{href}"
            title = (anchor.get_text() or "").strip()
            if not title:
                continue

            # Look for price in the enclosing card
            card = anchor.find_parent()
            card_text = card.get_text(" ", strip=True) if card else title
            price_m = _PRICE_RE.search(card_text)
            price = (
                float(price_m.group(1).replace(",", ""))
                if price_m
                else None
            )
            year_m = _YEAR_RE.search(title)
            year = int(year_m.group(1)) if year_m else None

            external_id = url.rstrip("/").rsplit("/", 1)[-1]
            yield NormalizedListing(
                source=self.name,
                external_id=external_id,
                url=url,
                title=title,
                year=year,
                price=price,
                raw={"source": "bookoo"},
            )
            yielded += 1
            if yielded >= limit:
                return

    async def aclose(self) -> None:
        await self._client.aclose()
