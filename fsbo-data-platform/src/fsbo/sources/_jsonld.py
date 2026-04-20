"""Shared helpers for source adapters that parse JSON-LD Vehicle/Product
blocks from listing HTML. Most FSBO marketplaces embed Schema.org-style
structured data; this lets each adapter stay small.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from fsbo.sources.base import NormalizedListing

_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")


def iter_jsonld_blocks(html: str) -> list[dict]:
    """Return every JSON-LD dict embedded in <script type="application/ld+json">."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        blocks = payload if isinstance(payload, list) else [payload]
        for block in blocks:
            if isinstance(block, dict):
                out.append(block)
    return out


def iter_vehicle_blocks(html: str) -> list[dict]:
    """JSON-LD blocks whose @type is Vehicle / Product / Car."""
    return [
        b for b in iter_jsonld_blocks(html)
        if b.get("@type") in ("Vehicle", "Product", "Car")
    ]


def parse_vehicle_block(
    block: dict[str, Any], source_name: str, fallback_url: str | None = None
) -> NormalizedListing | None:
    """Convert a Schema.org Vehicle/Product JSON-LD block into a
    NormalizedListing. Returns None if the block lacks a usable URL.
    """
    url = block.get("url") or fallback_url or ""
    if not url:
        return None
    external_id = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0] or url

    title = block.get("name")
    description = block.get("description")

    year: int | None = None
    ymd = block.get("vehicleModelDate") or block.get("modelDate")
    if ymd:
        try:
            year = int(str(ymd)[:4])
        except ValueError:
            year = None
    if not year and title:
        m = _YEAR_RE.search(title)
        if m:
            year = int(m.group(1))

    manufacturer = block.get("manufacturer")
    make = (
        manufacturer.get("name")
        if isinstance(manufacturer, dict)
        else manufacturer
    )
    model = block.get("model")

    mileage: int | None = None
    mraw = block.get("mileageFromOdometer") or {}
    if isinstance(mraw, dict):
        v = mraw.get("value")
        if v is not None:
            try:
                mileage = int(v)
            except (TypeError, ValueError):
                mileage = None
    elif mraw is not None:
        try:
            mileage = int(mraw)
        except (TypeError, ValueError):
            mileage = None

    price: float | None = None
    offers = block.get("offers") or {}
    if isinstance(offers, dict):
        raw = offers.get("price") or offers.get("highPrice") or offers.get("lowPrice")
        if raw is not None:
            try:
                price = float(raw)
            except (TypeError, ValueError):
                price = None

    vin = block.get("vehicleIdentificationNumber")

    images: list[str] = []
    image = block.get("image")
    if isinstance(image, str):
        images = [image]
    elif isinstance(image, list):
        images = [i for i in image if isinstance(i, str)][:8]

    return NormalizedListing(
        source=source_name,
        external_id=str(external_id),
        url=url,
        title=title if isinstance(title, str) else None,
        description=description if isinstance(description, str) else None,
        year=year,
        make=make if isinstance(make, str) else None,
        model=model if isinstance(model, str) else None,
        mileage=mileage,
        price=price,
        vin=vin if isinstance(vin, str) else None,
        images=images,
        raw={"jsonld": block},
    )
