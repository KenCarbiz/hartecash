"""Perceptual image hashing.

Used by the seller identity graph: dealers running multiple FB
profiles typically photograph cars against the same background (their
driveway, lot, or parking structure). A pHash of the listing image is
a cheap, deterministic fingerprint for that backdrop — even when the
foreground car changes.

We start with a whole-image pHash. A later iteration can crop to
background-only (top + bottom strips minus the car bounding box) for
more precise clustering; full-image hashes already catch most
reuse-the-same-shot-with-small-edits cases.

API is intentionally synchronous + Pillow-based so it's testable
without a browser.
"""

from __future__ import annotations

from io import BytesIO

import httpx
import imagehash
from PIL import Image, UnidentifiedImageError

from fsbo.logging import get_logger

log = get_logger(__name__)


def phash_bytes(blob: bytes) -> str | None:
    """Return the pHash hex of an image blob, or None if un-decodable."""
    try:
        with Image.open(BytesIO(blob)) as img:
            img.load()
            # Normalize to RGB for consistent hashes on transparent / palette images.
            if img.mode != "RGB":
                img = img.convert("RGB")
            return str(imagehash.phash(img))
    except (UnidentifiedImageError, OSError):
        return None


async def fetch_and_hash(url: str, client: httpx.AsyncClient | None = None) -> str | None:
    own = client is None
    if own:
        client = httpx.AsyncClient(timeout=20.0, follow_redirects=True)
    try:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            log.debug("image_hash.fetch_failed", url=url, error=str(e))
            return None
        return phash_bytes(resp.content)
    finally:
        if own:
            await client.aclose()
