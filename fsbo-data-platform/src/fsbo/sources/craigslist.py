"""Craigslist source.

Uses Craigslist's public RSS feeds (append ``&format=rss`` to any search URL).
RSS is explicitly provided for programmatic consumption, so this path has minimal
legal exposure compared to HTML scraping.

Search URL shape:
    https://{city}.craigslist.org/search/cta?postedToday=1&format=rss
where ``cta`` = "cars & trucks - by owner". Use ``ctd`` for dealer-only.
"""

import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import feedparser
import httpx
from dateutil import parser as dateparser

from fsbo.logging import get_logger
from fsbo.sources.base import NormalizedListing, Source

log = get_logger(__name__)

_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")
_PRICE_RE = re.compile(r"\$\s?([\d,]+)")
_MILES_RE = re.compile(r"([\d,]+)\s*(?:miles?|mi\b)", re.I)
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")


class CraigslistSource(Source):
    name = "craigslist"

    BY_OWNER = "cta"
    BY_DEALER = "ctd"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "fsbo-data-platform/0.0.1 (+contact@example.com)"},
            follow_redirects=True,
        )

    async def fetch(
        self,
        city: str = "tampa",
        category: str = BY_OWNER,
        posted_today: bool = True,
        min_price: int | None = None,
        max_price: int | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
        **_: Any,
    ) -> AsyncIterator[NormalizedListing]:
        params: dict[str, str] = {"format": "rss"}
        if posted_today:
            params["postedToday"] = "1"
        if min_price is not None:
            params["min_price"] = str(min_price)
        if max_price is not None:
            params["max_price"] = str(max_price)
        if min_year is not None:
            params["min_auto_year"] = str(min_year)
        if max_year is not None:
            params["max_auto_year"] = str(max_year)

        url = f"https://{city}.craigslist.org/search/{category}"
        log.info("craigslist.fetch", city=city, category=category, params=params)

        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)

        for entry in feed.entries:
            try:
                yield self._parse_entry(entry, city)
            except Exception as e:  # one bad entry shouldn't kill the run
                log.warning("craigslist.parse_error", error=str(e), entry_id=entry.get("id"))

    def _parse_entry(self, entry: Any, city: str) -> NormalizedListing:
        link: str = entry.get("link") or entry.get("id", "")
        external_id = self._extract_id(link)

        title: str = entry.get("title", "") or ""
        description: str = entry.get("summary", "") or ""
        blob = f"{title}\n{description}"

        year = self._extract_year(title)
        price = self._extract_price(title) or self._extract_price(description)
        mileage = self._extract_mileage(blob)
        vin = self._extract_vin(blob)

        posted_at: datetime | None = None
        if entry.get("updated"):
            try:
                posted_at = dateparser.parse(entry["updated"])
            except (ValueError, TypeError):
                posted_at = None

        return NormalizedListing(
            source=self.name,
            external_id=external_id,
            url=link,
            title=title,
            description=description,
            year=year,
            price=price,
            mileage=mileage,
            vin=vin,
            city=city,
            posted_at=posted_at,
            raw={"entry": {k: entry.get(k) for k in ("title", "summary", "link", "updated")}},
        )

    @staticmethod
    def _extract_id(link: str) -> str:
        # https://tampa.craigslist.org/hil/cto/d/tampa-2018-ford-f150/7712345678.html
        m = re.search(r"/(\d{10,})\.html", link)
        return m.group(1) if m else link

    @staticmethod
    def _extract_year(text: str) -> int | None:
        m = _YEAR_RE.search(text)
        return int(m.group(1)) if m else None

    @staticmethod
    def _extract_price(text: str) -> float | None:
        m = _PRICE_RE.search(text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _extract_mileage(text: str) -> int | None:
        m = _MILES_RE.search(text)
        if not m:
            return None
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _extract_vin(text: str) -> str | None:
        m = _VIN_RE.search(text.upper())
        return m.group(1) if m else None

    async def aclose(self) -> None:
        await self._client.aclose()
