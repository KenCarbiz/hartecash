"""Extension breakage-report endpoint.

Records FB Marketplace walker failures into ScrapeRun so the source-
health dashboard surfaces them alongside scheduler failures.
"""

from sqlalchemy import select

from fsbo.models import ScrapeRun


def test_breakage_creates_failed_scrape_run(client, db_session):
    r = client.post(
        "/telemetry/extension-breakage",
        json={
            "kind": "graphql_walker_empty",
            "url": "https://www.facebook.com/marketplace/category/vehicles",
            "user_agent": "Mozilla/5.0 ...",
            "extension_version": "0.1.0",
            "extra": {"tile_count_seen": 0},
        },
    )
    assert r.status_code == 204

    rows = db_session.scalars(
        select(ScrapeRun).where(ScrapeRun.source == "facebook_marketplace")
    ).all()
    assert len(rows) == 1
    row = rows[0]
    assert "graphql_walker_empty" in (row.error or "")
    assert row.params["telemetry"] == "graphql_walker_empty"
    assert row.params["dealer_id"] == "demo-dealer"
    assert row.params["extension_version"] == "0.1.0"
    assert row.params["tile_count_seen"] == 0
    assert row.finished_at is not None


def test_breakage_truncates_long_url(client, db_session):
    long_url = "https://fb.com/marketplace/" + "a" * 1000
    r = client.post(
        "/telemetry/extension-breakage",
        json={"kind": "dom_walker_empty", "url": long_url},
    )
    assert r.status_code == 204
    row = db_session.scalar(
        select(ScrapeRun).where(ScrapeRun.source == "facebook_marketplace")
    )
    assert len(row.params["url"]) == 500
