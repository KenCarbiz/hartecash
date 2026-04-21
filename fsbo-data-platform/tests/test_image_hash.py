from contextlib import contextmanager
from io import BytesIO

import httpx
import pytest
import respx
from PIL import Image

from fsbo.enrichment.image_hash import fetch_and_hash, phash_bytes
from fsbo.models import Listing, SellerIdentity


def _jpeg_bytes(seed: int = 0) -> bytes:
    """Generate a deterministic, *textured* test JPEG. pHash ignores flat
    color so we paint a per-pixel gradient tied to the seed."""
    img = Image.new("RGB", (64, 64))
    px = img.load()
    for y in range(64):
        for x in range(64):
            # seed determines the gradient direction/frequency
            r = (x * (seed * 3 + 1)) % 256
            g = (y * (seed * 5 + 2)) % 256
            b = ((x + y + seed) * 7) % 256
            px[x, y] = (r, g, b)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_phash_bytes_valid_image():
    h = phash_bytes(_jpeg_bytes(1))
    assert isinstance(h, str)
    assert len(h) == 16  # imagehash.phash default is 8x8 = 64-bit = 16 hex chars


def test_phash_bytes_invalid_returns_none():
    assert phash_bytes(b"not an image") is None
    assert phash_bytes(b"") is None


def test_phash_bytes_same_image_same_hash():
    h1 = phash_bytes(_jpeg_bytes(42))
    h2 = phash_bytes(_jpeg_bytes(42))
    assert h1 == h2


def test_phash_bytes_different_images_different_hash():
    h1 = phash_bytes(_jpeg_bytes(1))
    h2 = phash_bytes(_jpeg_bytes(200))
    assert h1 != h2


@pytest.mark.asyncio
async def test_fetch_and_hash_success():
    with respx.mock() as mock:
        mock.get("https://cdn.example.com/photo.jpg").mock(
            return_value=httpx.Response(200, content=_jpeg_bytes(7))
        )
        h = await fetch_and_hash(
            "https://cdn.example.com/photo.jpg",
            client=httpx.AsyncClient(),
        )
    assert isinstance(h, str)


@pytest.mark.asyncio
async def test_fetch_and_hash_404_returns_none():
    with respx.mock() as mock:
        mock.get("https://cdn.example.com/missing.jpg").mock(
            return_value=httpx.Response(404)
        )
        h = await fetch_and_hash(
            "https://cdn.example.com/missing.jpg",
            client=httpx.AsyncClient(),
        )
    assert h is None


# ----- Worker integration -----


@pytest.fixture
def _patch_image_worker_session(db_session, monkeypatch):
    @contextmanager
    def fake_scope():
        yield db_session

    monkeypatch.setattr("fsbo.workers.image_worker.session_scope", fake_scope)


@pytest.mark.asyncio
async def test_image_worker_hashes_and_registers(
    db_session, _patch_image_worker_session, monkeypatch
):
    # Seed a listing with two image URLs
    listing = Listing(
        source="facebook_marketplace",
        external_id="img-1",
        url="http://x",
        title="2020 F-150",
        classification="private_seller",
        images=[
            "https://cdn.example.com/a.jpg",
            "https://cdn.example.com/b.jpg",
        ],
        seller_phone="(555) 100-0001",
    )
    db_session.add(listing)
    db_session.flush()

    # Mock fetch_and_hash to return deterministic phashes
    calls: list[str] = []

    async def fake_fetch_and_hash(url: str, client=None):
        calls.append(url)
        return f"hash_for_{url.rsplit('/', 1)[-1]}"

    monkeypatch.setattr(
        "fsbo.workers.image_worker.fetch_and_hash", fake_fetch_and_hash
    )

    from fsbo.workers.image_worker import run

    stats = await run(max_listings=10)
    assert stats["attempted"] == 1
    assert stats["hashed"] == 1

    # Listing row now carries the hashes
    row = db_session.query(Listing).filter_by(external_id="img-1").first()
    assert row.raw.get("image_bg_phashes") == [
        "hash_for_a.jpg",
        "hash_for_b.jpg",
    ]
    assert row.raw.get("image_hash_attempted_at")

    # Seller-graph identities now include an image_phash node per hash
    phash_idents = (
        db_session.query(SellerIdentity).filter_by(kind="image_phash").all()
    )
    values = {i.value for i in phash_idents}
    assert "hash_for_a.jpg" in values
    assert "hash_for_b.jpg" in values


@pytest.mark.asyncio
async def test_image_worker_skips_recently_hashed(
    db_session, _patch_image_worker_session, monkeypatch
):
    from datetime import datetime, timedelta, timezone

    attempted = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    listing = Listing(
        source="facebook_marketplace",
        external_id="img-skip",
        url="http://x",
        title="2020 F-150",
        classification="private_seller",
        images=["https://cdn.example.com/x.jpg"],
        raw={
            "image_bg_phashes": ["old_hash"],
            "image_hash_attempted_at": attempted,
        },
    )
    db_session.add(listing)
    db_session.flush()

    calls: list[str] = []

    async def fake_fetch_and_hash(url: str, client=None):
        calls.append(url)
        return "new"

    monkeypatch.setattr(
        "fsbo.workers.image_worker.fetch_and_hash", fake_fetch_and_hash
    )

    from fsbo.workers.image_worker import run

    await run(max_listings=10)
    # Within the 14-day cooldown, skipped.
    assert calls == []
