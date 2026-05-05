"""Mirror Facebook Marketplace photos to local storage before they expire.

FB serves listing photos from `scontent-*.fbcdn.net` and `*.fbcdn.net`.
Two problems for us:

  1. URLs expire (signed token in the path) — usually within hours to a
     day. By the time a dealer opens the listing detail page tomorrow,
     the original URL 403s.
  2. FB rejects fetches with the wrong `Referer` header. A backend cron
     pulling images cold gets blocked.

Solution: when the extension ingests a FB listing, queue a mirror job
that downloads each image with the right Referer and writes it to
local storage (today: filesystem; tomorrow: S3-compatible object
store via the same interface).

The proxy route `/listings/{id}/image/{idx}` serves the mirrored copy.
The original URL stays in `Listing.images` as a fallback for non-FB
sources where we don't need to mirror.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Configurable via env. Defaults to ./var/images so dev "just works".
MIRROR_ROOT = Path(os.environ.get("FSBO_MEDIA_ROOT", "var/images"))

# Hosts whose images we MUST mirror (URLs expire). For other sources we
# leave the original URL alone.
MUST_MIRROR_HOSTS = (
    "scontent.fbcdn.net",
    "fbcdn.net",
    "scontent",  # match scontent-iad3-2.fbcdn.net etc via "in"
)


def must_mirror(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return any(needle in host for needle in MUST_MIRROR_HOSTS)


def storage_key(url: str) -> str:
    """Stable, deterministic on-disk key for a given image URL.

    Hash the URL minus its expiring query string, so re-ingest of the
    same photo from a different signed URL hits the same file.
    """
    parsed = urlparse(url)
    canon = f"{parsed.netloc}{parsed.path}"
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    # Two-level fanout to keep directories small at scale.
    return f"{digest[:2]}/{digest[2:4]}/{digest}.jpg"


def local_path(key: str) -> Path:
    return MIRROR_ROOT / key


def is_mirrored(url: str) -> bool:
    return local_path(storage_key(url)).exists()


def mirror_one(url: str, *, timeout: float = 8.0) -> str | None:
    """Download `url` and write it under MIRROR_ROOT. Returns the storage
    key on success, None on failure. Idempotent: if the file already
    exists, skips the network call.
    """
    key = storage_key(url)
    dest = local_path(key)
    if dest.exists():
        return key

    headers = {
        # Without facebook.com Referer, FB CDN often returns 403.
        "Referer": "https://www.facebook.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            r = c.get(url, headers=headers)
            r.raise_for_status()
            body = r.content
    except (httpx.HTTPError, httpx.HTTPStatusError) as exc:
        logger.warning("mirror_failed url=%s err=%s", url, exc)
        return None

    if not body or len(body) < 100:
        # FB sometimes returns a 1x1 spacer GIF on token expiry.
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return key


def mirror_listing_images(image_urls: list[str]) -> list[str]:
    """Mirror every URL that needs mirroring, return the list of storage
    keys that succeeded. Best-effort: failures are logged but don't
    abort the batch.
    """
    out: list[str] = []
    for url in image_urls:
        if not must_mirror(url):
            continue
        key = mirror_one(url)
        if key:
            out.append(key)
    return out
