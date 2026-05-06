"""Pluggable media-storage backend.

Two implementations:

  LocalFsStorage  — writes to MIRROR_ROOT on disk. Default. Fine for
    a single-instance deploy. Lost on Fly redeploy because Fly's
    filesystem is ephemeral.

  S3Storage  — writes to any S3-compatible bucket (AWS S3, Cloudflare
    R2, Backblaze B2, Wasabi, MinIO). Selected when FSBO_MEDIA_BACKEND
    is "s3" and the bucket env is configured. The serve() path
    streams bytes through us rather than redirecting so the browser
    never sees the bucket URL — keeps the dealer's photos behind our
    auth gate.

Both expose the same `exists / put / serve` surface so
fsbo.media.mirror swaps backends without code changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse


class MediaStorage(Protocol):
    name: str

    def exists(self, key: str) -> bool: ...

    def put(self, key: str, body: bytes) -> None: ...

    def serve(self, key: str) -> Response: ...


# -- Local filesystem ----------------------------------------------------


class LocalFsStorage:
    name = "local"

    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / key

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def put(self, key: str, body: bytes) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)

    def serve(self, key: str) -> Response:
        path = self._path(key)
        if not path.exists():
            raise HTTPException(404, "image missing on disk")
        return FileResponse(path, media_type="image/jpeg")


# -- S3 / S3-compatible --------------------------------------------------


class S3Storage:
    """S3-compatible (AWS S3, Cloudflare R2, Backblaze B2, MinIO).

    Lazy-imports boto3 so the dependency is optional in dev/CI. When
    the bucket env vars aren't configured the factory falls back to
    LocalFsStorage automatically.
    """

    name = "s3"

    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ):
        try:
            import boto3  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "S3 backend requested but boto3 not installed; run `uv add boto3`"
            ) from e

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def put(self, key: str, body: bytes) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="image/jpeg",
            CacheControl="public, max-age=86400",
        )

    def serve(self, key: str) -> Response:
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(404, f"image not in bucket: {exc}") from exc
        body = obj["Body"]

        # Stream the body through us — never expose the bucket URL.
        def _iter():
            for chunk in iter(lambda: body.read(64 * 1024), b""):
                yield chunk

        return StreamingResponse(_iter(), media_type="image/jpeg")


# -- Factory -------------------------------------------------------------


_DEFAULT_ROOT = Path(os.environ.get("FSBO_MEDIA_ROOT", "var/images"))


def make_storage() -> MediaStorage:
    """Pick a backend based on env. Falls back to local FS when S3 is
    requested but not fully configured (dev / CI safety)."""
    backend = (os.environ.get("FSBO_MEDIA_BACKEND") or "local").lower()
    if backend != "s3":
        return LocalFsStorage(_DEFAULT_ROOT)

    bucket = os.environ.get("FSBO_S3_BUCKET")
    region = os.environ.get("FSBO_S3_REGION") or "us-east-1"
    endpoint = os.environ.get("FSBO_S3_ENDPOINT_URL") or None
    access_key = os.environ.get("FSBO_S3_ACCESS_KEY_ID") or None
    secret_key = os.environ.get("FSBO_S3_SECRET_ACCESS_KEY") or None
    if not bucket:
        # Misconfigured — fall back rather than crash on import.
        return LocalFsStorage(_DEFAULT_ROOT)

    return S3Storage(
        bucket=bucket,
        region=region,
        endpoint_url=endpoint,
        access_key_id=access_key,
        secret_access_key=secret_key,
    )
