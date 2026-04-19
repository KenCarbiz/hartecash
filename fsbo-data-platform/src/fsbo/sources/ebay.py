"""eBay Motors source via the official Browse API.

Uses eBay's OAuth2 Browse API — the legitimate path. No scraping risk.
Requires EBAY_APP_ID / EBAY_CERT_ID for token fetch.

Docs: https://developer.ebay.com/api-docs/buy/browse/overview.html
Category ID 6001 = eBay Motors (passenger vehicles).
"""

import base64
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx
from dateutil import parser as dateparser

from fsbo.config import settings
from fsbo.logging import get_logger
from fsbo.sources.base import NormalizedListing, Source

log = get_logger(__name__)

_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_VEHICLES_CATEGORY = "6001"


class EbayMotorsSource(Source):
    name = "ebay_motors"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._token: str | None = None
        self._token_expires_at: float = 0

    async def _get_token(self) -> str:
        if not (settings.ebay_app_id and settings.ebay_cert_id):
            raise RuntimeError(
                "EBAY_APP_ID and EBAY_CERT_ID must be set. Register at "
                "https://developer.ebay.com/my/keys"
            )
        creds = base64.b64encode(
            f"{settings.ebay_app_id}:{settings.ebay_cert_id}".encode()
        ).decode()
        resp = await self._client.post(
            _TOKEN_URL,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload["access_token"]

    async def fetch(
        self,
        q: str | None = None,
        zip_code: str | None = None,
        radius_miles: int = 100,
        limit: int = 50,
        **_: Any,
    ) -> AsyncIterator[NormalizedListing]:
        token = await self._get_token()
        params: dict[str, Any] = {
            "category_ids": _VEHICLES_CATEGORY,
            "limit": str(min(limit, 200)),
        }
        if q:
            params["q"] = q
        filters = []
        if zip_code:
            filters.append(f"pickupCountry:US,pickupPostalCode:{zip_code},pickupRadius:{radius_miles}")
        if filters:
            params["filter"] = ",".join(filters)

        log.info("ebay.fetch", params=params)
        resp = await self._client.get(
            _BROWSE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": settings.ebay_marketplace,
            },
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("itemSummaries", []) or []:
            yield self._parse_item(item)

    def _parse_item(self, item: dict[str, Any]) -> NormalizedListing:
        price_obj = item.get("price") or {}
        price = float(price_obj.get("value", 0)) or None

        location = item.get("itemLocation") or {}
        images = []
        if item.get("image", {}).get("imageUrl"):
            images.append(item["image"]["imageUrl"])
        images.extend(img.get("imageUrl") for img in item.get("additionalImages", []) if img.get("imageUrl"))

        posted_at: datetime | None = None
        if item.get("itemCreationDate"):
            try:
                posted_at = dateparser.parse(item["itemCreationDate"])
            except (ValueError, TypeError):
                posted_at = None

        return NormalizedListing(
            source=self.name,
            external_id=str(item.get("itemId", "")),
            url=item.get("itemWebUrl", ""),
            title=item.get("title"),
            price=price,
            city=location.get("city"),
            state=location.get("stateOrProvince"),
            zip_code=location.get("postalCode"),
            images=images,
            posted_at=posted_at,
            raw={"item": item},
        )

    async def aclose(self) -> None:
        await self._client.aclose()
