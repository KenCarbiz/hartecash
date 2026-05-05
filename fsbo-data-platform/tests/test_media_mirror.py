"""Photo mirror module — downloads FB CDN images before they expire.

Tests stub the network so they're fully offline.
"""

import httpx
import pytest

from fsbo.media import mirror as media_mirror


@pytest.fixture
def tmp_root(tmp_path, monkeypatch):
    monkeypatch.setattr(media_mirror, "MIRROR_ROOT", tmp_path)
    return tmp_path


def _patch_httpx(monkeypatch, body: bytes, status: int) -> None:
    """Patch httpx.Client used inside mirror.py to use a MockTransport.
    Captures the original constructor first so we don't recurse."""
    original_client = httpx.Client
    transport = httpx.MockTransport(lambda req: httpx.Response(status, content=body))

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return original_client(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)


def test_must_mirror_recognizes_fb_cdn():
    assert media_mirror.must_mirror(
        "https://scontent-iad3-2.fbcdn.net/v/t39/abc.jpg"
    )
    assert media_mirror.must_mirror(
        "https://scontent.fbcdn.net/v/t39/abc.jpg"
    )


def test_must_mirror_skips_non_fb():
    assert not media_mirror.must_mirror(
        "https://images.craigslist.org/00X0X.jpg"
    )
    assert not media_mirror.must_mirror("not a url")


def test_storage_key_strips_query_string():
    """Same canonical path -> same key, even with rotating signed tokens."""
    a = media_mirror.storage_key(
        "https://scontent.fbcdn.net/v/t39/abc.jpg?token=sig1"
    )
    b = media_mirror.storage_key(
        "https://scontent.fbcdn.net/v/t39/abc.jpg?token=sig2"
    )
    assert a == b
    assert a.endswith(".jpg")
    assert a.count("/") == 2  # two-level fanout: aa/bb/<digest>.jpg


def test_mirror_one_writes_file(tmp_root, monkeypatch):
    payload = b"\xff\xd8\xff" + b"PHOTO_BYTES" * 50  # JPEG magic + filler
    _patch_httpx(monkeypatch, payload, status=200)
    url = "https://scontent.fbcdn.net/v/t39/photo1.jpg?token=abc"
    key = media_mirror.mirror_one(url)
    assert key
    assert (tmp_root / key).read_bytes() == payload


def test_mirror_one_skips_when_already_mirrored(tmp_root, monkeypatch):
    url = "https://scontent.fbcdn.net/v/t39/photo2.jpg"
    key = media_mirror.storage_key(url)
    dest = tmp_root / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"existing")

    def boom(*a, **kw):
        raise AssertionError("network call should have been skipped")

    monkeypatch.setattr(httpx, "Client", boom)
    assert media_mirror.mirror_one(url) == key


def test_mirror_one_returns_none_on_tiny_response(tmp_root, monkeypatch):
    _patch_httpx(monkeypatch, b"x" * 5, status=200)
    assert (
        media_mirror.mirror_one("https://scontent.fbcdn.net/v/t39/expired.jpg")
        is None
    )


def test_mirror_one_swallows_http_errors(tmp_root, monkeypatch):
    _patch_httpx(monkeypatch, b"forbidden", status=403)
    assert (
        media_mirror.mirror_one("https://scontent.fbcdn.net/v/t39/blocked.jpg")
        is None
    )


def test_mirror_listing_images_filters_and_returns_keys(tmp_root, monkeypatch):
    payload = b"\xff\xd8\xff" + b"P" * 200
    _patch_httpx(monkeypatch, payload, status=200)
    keys = media_mirror.mirror_listing_images(
        [
            "https://scontent.fbcdn.net/v/t39/a.jpg",
            "https://images.craigslist.org/0.jpg",  # skipped (non-FB)
            "https://scontent.fbcdn.net/v/t39/b.jpg",
        ]
    )
    assert len(keys) == 2
    for k in keys:
        assert (tmp_root / k).exists()
