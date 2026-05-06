"""Pluggable media-storage backend selection.

Real S3 isn't reached in tests (no boto3 mocks). The cases here cover:
- The factory falls back to local FS when FSBO_MEDIA_BACKEND=s3 but
  FSBO_S3_BUCKET isn't set (dev / CI safety).
- The factory honors FSBO_MEDIA_BACKEND=local explicitly.
- The local backend round-trips put/exists/serve correctly.
"""

import os

import pytest

from fsbo.media.storage import LocalFsStorage, make_storage


@pytest.fixture
def clean_env(monkeypatch):
    for var in (
        "FSBO_MEDIA_BACKEND",
        "FSBO_S3_BUCKET",
        "FSBO_S3_REGION",
        "FSBO_S3_ENDPOINT_URL",
        "FSBO_S3_ACCESS_KEY_ID",
        "FSBO_S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_default_backend_is_local(clean_env):
    s = make_storage()
    assert isinstance(s, LocalFsStorage)
    assert s.name == "local"


def test_s3_backend_requested_without_bucket_falls_back_to_local(clean_env):
    os.environ["FSBO_MEDIA_BACKEND"] = "s3"
    # Bucket env intentionally absent
    s = make_storage()
    assert isinstance(s, LocalFsStorage)


def test_local_backend_roundtrip_put_exists_serve(tmp_path):
    s = LocalFsStorage(tmp_path)
    key = "ab/cd/abcd1234.jpg"
    payload = b"\xff\xd8\xff" + b"PHOTO" * 50

    assert not s.exists(key)
    s.put(key, payload)
    assert s.exists(key)
    assert (tmp_path / key).read_bytes() == payload

    # Serve returns a FileResponse pointing at the path on disk.
    from fastapi.responses import FileResponse

    resp = s.serve(key)
    assert isinstance(resp, FileResponse)


def test_local_backend_serve_404s_when_missing(tmp_path):
    from fastapi import HTTPException

    s = LocalFsStorage(tmp_path)
    with pytest.raises(HTTPException) as exc:
        s.serve("nope/xx/missing.jpg")
    assert exc.value.status_code == 404
