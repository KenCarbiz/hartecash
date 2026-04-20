from datetime import datetime, timedelta, timezone

from fsbo.models import Listing, ScrapeRun


def test_source_health_aggregates(client, db_session):
    now = datetime.now(timezone.utc)
    db_session.add(
        Listing(
            source="craigslist",
            external_id="cl-1",
            url="http://x",
            classification="private_seller",
            first_seen_at=now - timedelta(hours=2),
        )
    )
    db_session.add(
        Listing(
            source="craigslist",
            external_id="cl-2",
            url="http://y",
            classification="private_seller",
            first_seen_at=now - timedelta(days=3),
        )
    )
    db_session.add(
        Listing(
            source="ksl",
            external_id="ksl-1",
            url="http://z",
            classification="private_seller",
            first_seen_at=now - timedelta(hours=1),
        )
    )
    db_session.add(
        ScrapeRun(
            source="craigslist",
            params={"city": "tampa"},
            started_at=now - timedelta(minutes=30),
            finished_at=now - timedelta(minutes=29),
            fetched_count=10,
            inserted_count=2,
            updated_count=0,
        )
    )
    db_session.flush()

    r = client.get("/sources/health")
    assert r.status_code == 200
    payload = r.json()
    by_source = {p["source"]: p for p in payload}
    assert by_source["craigslist"]["total_listings"] == 2
    assert by_source["craigslist"]["listings_last_24h"] == 1
    assert by_source["craigslist"]["listings_last_7d"] == 2
    assert by_source["craigslist"]["last_scrape_at"] is not None
    assert by_source["craigslist"]["recent_inserted"] == 2
    assert by_source["ksl"]["listings_last_24h"] == 1


def test_scrape_runs_endpoint(client, db_session):
    now = datetime.now(timezone.utc)
    for i in range(3):
        db_session.add(
            ScrapeRun(
                source="craigslist",
                params={"iter": i},
                started_at=now - timedelta(minutes=10 * (i + 1)),
                fetched_count=i * 5,
            )
        )
    db_session.flush()

    r = client.get("/sources/runs?source=craigslist&limit=5")
    assert r.status_code == 200
    assert len(r.json()) == 3
