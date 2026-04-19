"""Dedup fingerprint. Same car across multiple sources should collapse."""

import hashlib
import re

from fsbo.sources.base import NormalizedListing


def compute_dedup_key(listing: NormalizedListing) -> str | None:
    """VIN is the strongest signal; fall back to a phone+vehicle fingerprint."""
    if listing.vin:
        return f"vin:{listing.vin.upper()}"

    phone = _normalize_phone(listing.seller_phone)
    if phone and listing.year and listing.make:
        parts = [phone, str(listing.year), listing.make.lower(), (listing.model or "").lower()]
        h = hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]
        return f"phv:{h}"

    return None


def _normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None
