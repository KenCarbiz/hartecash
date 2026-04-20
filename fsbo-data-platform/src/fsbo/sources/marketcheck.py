"""Marketcheck API (marketcheck.com) source — LEGAL paid aggregator.

Marketcheck licenses listing data from Autotrader, Cars.com, CarGurus,
Edmunds, TrueCar, and 20+ other sites. This is the 100%-legitimate path
to get content that's otherwise gated by strict anti-scrape ToS.

Pricing (2025): roughly $1k-$5k/mo depending on volume.
Docs: https://apidocs.marketcheck.com/

This adapter is a stub until MARKETCHECK_API_KEY is set. Once the
contract is signed and the key populated, it yields real listings
across the major mainstream sites that we deliberately don't scrape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from fsbo.config import settings
from fsbo.logging import get_logger
from fsbo.sources.base import NormalizedListing, Source
from fsbo.sources.rate_limit import throttle

log = get_logger(__name__)

_SEARCH_URL = "https://api.marketcheck.com/v2/search/car/active"


class MarketcheckSource(Source):
    name = "marketcheck"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def fetch(
        self,
        make: str | None = None,
        model: str | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        zip_code: str | None = None,
        radius_miles: int = 100,
        limit: int = 50,
        seller_type: str = "private",
        **_: Any,
    ) -> AsyncIterator[NormalizedListing]:
        if not settings.marketcheck_api_key:
            log.info(
                "marketcheck.no_api_key",
                message=(
                    "MARKETCHECK_API_KEY not set — adapter yields no results. "
                    "Sign a contract at marketcheck.com to enable."
                ),
            )
            return

        params: dict[str, Any] = {
            "api_key": settings.marketcheck_api_key,
            "rows": min(limit, 50),
            "seller_type": seller_type,  # private | dealer | all
            "include_relevant_links": "true",
        }
        if make:
            params["make"] = make
        if model:
            params["model"] = model
        if year_min is not None:
            params["year_min"] = year_min
        if year_max is not None:
            params["year_max"] = year_max
        if zip_code:
            params["zip"] = zip_code
            params["radius"] = radius_miles

        await throttle("marketcheck")
        try:
            resp = await self._client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("marketcheck.fetch_failed", error=str(e))
            return

        payload = resp.json()
        for item in payload.get("listings", []) or []:
            norm = self._parse(item)
            if norm:
                yield norm

    def _parse(self, item: dict[str, Any]) -> NormalizedListing | None:
        vin = item.get("vin")
        vdp = item.get("vdp_url") or item.get("href")
        external_id = item.get("id") or vin or vdp
        if not external_id or not vdp:
            return None

        build = item.get("build") or {}
        media = item.get("media") or {}
        dealer = item.get("dealer") or {}

        images: list[str] = []
        photos = media.get("photo_links") or []
        if isinstance(photos, list):
            images = [p for p in photos if isinstance(p, str)][:8]

        price = None
        raw_price = item.get("price")
        if raw_price is not None:
            try:
                price = float(raw_price)
            except (TypeError, ValueError):
                price = None

        mileage = None
        raw_miles = item.get("miles")
        if raw_miles is not None:
            try:
                mileage = int(raw_miles)
            except (TypeError, ValueError):
                mileage = None

        # Marketcheck's `source` field identifies the origin site
        # (autotrader, cars.com, cargurus, etc). We prefix our source
        # name so downstream filters can pivot on it.
        origin = str(item.get("source") or "unknown").lower()

        return NormalizedListing(
            source=f"{self.name}:{origin}",
            external_id=str(external_id),
            url=vdp,
            title=f"{build.get('year', '')} {build.get('make', '')} {build.get('model', '')}".strip() or None,
            description=item.get("heading"),
            year=build.get("year") if isinstance(build.get("year"), int) else None,
            make=build.get("make") if isinstance(build.get("make"), str) else None,
            model=build.get("model") if isinstance(build.get("model"), str) else None,
            trim=build.get("trim") if isinstance(build.get("trim"), str) else None,
            mileage=mileage,
            price=price,
            vin=vin if isinstance(vin, str) else None,
            city=dealer.get("city") if isinstance(dealer.get("city"), str) else None,
            state=dealer.get("state") if isinstance(dealer.get("state"), str) else None,
            zip_code=dealer.get("zip") if isinstance(dealer.get("zip"), str) else None,
            seller_phone=dealer.get("phone") if isinstance(dealer.get("phone"), str) else None,
            images=images,
            raw={"marketcheck": item},
        )

    async def aclose(self) -> None:
        await self._client.aclose()
