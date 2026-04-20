"""ClassicCars.com source — classic FSBO marketplace.

~40% FSBO mix, national coverage for classics. Like Hemmings, sellers
pay to list so search-engine indexing is allowed. Detail pages embed
Vehicle JSON-LD.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from fsbo.config import settings
from fsbo.logging import get_logger
from fsbo.sources._jsonld import iter_vehicle_blocks, parse_vehicle_block
from fsbo.sources.base import NormalizedListing, Source
from fsbo.sources.rate_limit import throttle

log = get_logger(__name__)

_SEARCH_URL = "https://classiccars.com/listings/find"


class ClassicCarsSource(Source):
    name = "classic_cars"

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
        year_min: int | None = None,
        year_max: int | None = None,
        limit: int = 30,
        **_: Any,
    ) -> AsyncIterator[NormalizedListing]:
        params: dict[str, str] = {"sellerType": "private"}
        if make:
            params["make"] = make
        if year_min is not None:
            params["yearFrom"] = str(year_min)
        if year_max is not None:
            params["yearTo"] = str(year_max)

        await throttle("classic_cars")
        try:
            resp = await self._client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("classic_cars.fetch_failed", error=str(e))
            return

        yielded = 0
        for block in iter_vehicle_blocks(resp.text):
            listing = parse_vehicle_block(block, self.name)
            if listing:
                yielded += 1
                yield listing
                if yielded >= limit:
                    return

    async def aclose(self) -> None:
        await self._client.aclose()
