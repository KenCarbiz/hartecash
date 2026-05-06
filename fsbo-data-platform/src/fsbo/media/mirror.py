"""Mirror Facebook Marketplace photos to durable storage before they expire.

FB serves listing photos from `scontent-*.fbcdn.net` and `*.fbcdn.net`.
Two problems for us:

  1. URLs expire (signed token in the path) — usually within hours to a
     day. By the time a dealer opens the listing detail page tomorrow,
     the original URL 403s.
  2. FB rejects fetches with the wrong `Referer` header. A backend cron
     pulling images cold gets blocked.

Solution: when the extension ingests a FB listing, queue a mirror job
that downloads each image with the right Referer and writes it via the
configured storage backend (local FS for dev, S3-compatible in prod —
see fsbo.media.storage).

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
from fastapi.responses import Response

from fsbo.media.storage import LocalFsStorage, MediaStorage, make_storage

logger = logging.getLogger(__name__)

# Kept for back-compat: tests monkeypatch this attribute and expect
# writes to land under it. The active backend is computed per-call so
# the monkeypatch always wins.
MIRROR_ROOT = Path(os.environ.get("FSBO_MEDIA_ROOT", "var/images"))

# Hosts whose images we MUST mirror (URLs expire). For other sources we
# leave the original URL alone.
MUST_MIRROR_HOSTS = (
    "scontent.fbcdn.net",
    "fbcdn.net",
    "scontent",  # match scontent-iad3-2.fbcdn.net etc via "in"
)


def _storage() -> MediaStorage:
    """Resolve the active backend. When FSBO_MEDIA_BACKEND=s3 + bucket
    env is configured, use S3; otherwise local FS rooted at MIRROR_ROOT
    (which tests monkeypatch). No caching — keeps test isolation tight
    and the cost is negligible.
    """
    backend = make_storage()
    if isinstance(backend, LocalFsStorage):
        # Honor the test-mode monkeypatch on MIRROR_ROOT.
        return LocalFsStorage(MIRROR_ROOT)
    return backend


def must_mirror(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return any(needle in host for needle in MUST_MIRROR_HOSTS)


def storage_key(url: str) -> str:
    """Stable, deterministic key for a given image URL.

    Hash the URL minus its expiring query string, so re-ingest of the
    same photo from a different signed URL hits the same key.
    """
    parsed = urlparse(url)
    canon = f"{parsed.netloc}{parsed.path}"
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    # Two-level fanout to keep directories / S3 prefixes small at scale.
    return f"{digest[:2]}/{digest[2:4]}/{digest}.jpg"


def local_path(key: str) -> Path:
    """Disk path for the local-FS backend. Kept for tests that inspect
    the on-disk layout directly. Returns a path even when the active
    backend is S3 — caller is expected to know which backend is on."""
    return MIRROR_ROOT / key


def is_mirrored(url: str) -> bool:
    return _storage().exists(storage_key(url))


def serve_image(key: str) -> Response:
    """Backend-agnostic image serve. Used by the proxy route."""
    return _storage().serve(key)


def mirror_one(url: str, *, timeout: float = 8.0) -> str | None:
    """Download `url` and write via the active storage backend.
    Returns the storage key on success, None on failure. Idempotent:
    if the key already exists, skips the network call."""
    key = storage_key(url)
    storage = _storage()
    if storage.exists(key):
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

    storage.put(key, body)
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
