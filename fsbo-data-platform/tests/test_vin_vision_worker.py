from contextlib import contextmanager

import pytest

from fsbo.models import Listing


@pytest.fixture(autouse=True)
def _patch_session_scope(db_session, monkeypatch):
    """The worker calls session_scope() directly. Route it to our test
    in-memory session so the worker sees the same DB as the test."""

    @contextmanager
    def fake_scope():
        yield db_session

    monkeypatch.setattr(
        "fsbo.workers.vin_vision_worker.session_scope", fake_scope
    )


@pytest.fixture
def seed_listings(db_session):
    """Seed a mix of listings that should vs shouldn't trigger vision."""
    rows = [
        # score 75, $15k, no VIN, images -> eligible
        Listing(
            source="facebook_marketplace",
            external_id="eligible-1",
            url="http://x/1",
            title="2019 F-150",
            year=2019,
            make="Ford",
            model="F-150",
            price=15000,
            classification="private_seller",
            lead_quality_score=75,
            images=["https://cdn.fake/1.jpg", "https://cdn.fake/2.jpg"],
        ),
        # score too low -> skip
        Listing(
            source="facebook_marketplace",
            external_id="low-score",
            url="http://x/2",
            title="2018 Malibu",
            price=12000,
            classification="private_seller",
            lead_quality_score=30,
            images=["https://cdn.fake/3.jpg"],
        ),
        # has VIN already -> skip
        Listing(
            source="facebook_marketplace",
            external_id="has-vin",
            url="http://x/3",
            title="2020 Civic",
            price=17000,
            classification="private_seller",
            lead_quality_score=80,
            vin="1HGBH41JXMN109186",
            images=["https://cdn.fake/4.jpg"],
        ),
        # auto_hidden -> skip
        Listing(
            source="facebook_marketplace",
            external_id="hidden",
            url="http://x/4",
            title="shipping-only scam",
            price=20000,
            classification="private_seller",
            lead_quality_score=85,
            auto_hidden=True,
            auto_hide_reason="scam_score>=0.9",
            images=["https://cdn.fake/5.jpg"],
        ),
        # no images -> skip
        Listing(
            source="facebook_marketplace",
            external_id="no-images",
            url="http://x/5",
            title="2019 Tacoma",
            price=18000,
            classification="private_seller",
            lead_quality_score=80,
            images=[],
        ),
        # price too low -> skip
        Listing(
            source="facebook_marketplace",
            external_id="too-cheap",
            url="http://x/6",
            title="1998 Civic beater",
            price=1500,
            classification="private_seller",
            lead_quality_score=70,
            images=["https://cdn.fake/6.jpg"],
        ),
    ]
    for r in rows:
        db_session.add(r)
    db_session.flush()
    return rows


@pytest.mark.asyncio
async def test_worker_only_picks_eligible(seed_listings, monkeypatch):
    from fsbo.workers.vin_vision_worker import run

    calls: list[list[str]] = []

    async def fake_extract(images):
        calls.append(list(images))
        from fsbo.enrichment.vin_vision import VisionVinResult

        return VisionVinResult(vin=None, checked_images=len(images), source_image=None)

    monkeypatch.setattr(
        "fsbo.workers.vin_vision_worker.extract_vin_from_images", fake_extract
    )

    stats = await run(max_listings=10, min_score=55, min_price=5000)
    # Only the "eligible-1" listing passes all gates
    assert stats["attempted"] == 1
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_worker_records_found_vin(seed_listings, db_session, monkeypatch):
    from fsbo.enrichment.vin_vision import VisionVinResult
    from fsbo.workers.vin_vision_worker import run

    async def fake_extract(images):
        return VisionVinResult(
            vin="1M8GDM9AXKP042788",
            checked_images=1,
            source_image="https://cdn.fake/1.jpg",
        )

    async def fake_decode(vin):
        from fsbo.enrichment.vin import DecodedVin

        return DecodedVin(
            vin=vin, year=1989, make="Freightliner", model="FLD", error_code="0"
        )

    monkeypatch.setattr(
        "fsbo.workers.vin_vision_worker.extract_vin_from_images", fake_extract
    )
    monkeypatch.setattr("fsbo.workers.vin_vision_worker.decode_vin", fake_decode)

    await run(max_listings=10)
    row = db_session.query(Listing).filter_by(external_id="eligible-1").first()
    assert row.vin == "1M8GDM9AXKP042788"
    assert row.raw.get("vin_vision_source_image") == "https://cdn.fake/1.jpg"
    assert row.raw.get("vin_vision_attempted_at")


@pytest.mark.asyncio
async def test_worker_skips_recently_attempted(db_session, monkeypatch):
    # Seed a listing that "was attempted yesterday"
    from datetime import datetime, timedelta, timezone

    attempted_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    row = Listing(
        source="facebook_marketplace",
        external_id="recent-attempt",
        url="http://x",
        title="2019 F-150",
        price=15000,
        classification="private_seller",
        lead_quality_score=75,
        images=["https://cdn.fake/1.jpg"],
        raw={"vin_vision_attempted_at": attempted_at},
    )
    db_session.add(row)
    db_session.flush()

    calls = []

    async def fake_extract(images):
        calls.append(images)
        from fsbo.enrichment.vin_vision import VisionVinResult

        return VisionVinResult(vin=None, checked_images=0, source_image=None)

    monkeypatch.setattr(
        "fsbo.workers.vin_vision_worker.extract_vin_from_images", fake_extract
    )
    from fsbo.workers.vin_vision_worker import run

    await run(max_listings=10)
    # Nothing was called because the 7-day cooldown applies
    assert calls == []
