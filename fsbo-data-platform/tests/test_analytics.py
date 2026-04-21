from datetime import datetime, timedelta, timezone

from fsbo.models import Interaction, Lead, Listing


def _add_listing(db, **kw):
    base = {
        "source": "craigslist",
        "external_id": f"ext-{id(kw)}",
        "url": "http://x",
        "title": "Some car",
        "classification": "private_seller",
        "auto_hidden": False,
    }
    base.update(kw)
    row = Listing(**base)
    db.add(row)
    db.flush()
    return row


def _add_lead(db, listing_id, dealer_id="demo-dealer", status="new"):
    now = datetime.now(timezone.utc)
    lead = Lead(
        dealer_id=dealer_id,
        listing_id=listing_id,
        status=status,
        created_at=now,
        updated_at=now,
    )
    db.add(lead)
    db.flush()
    return lead


def test_funnel_empty_defaults(client):
    r = client.get("/analytics/funnel", headers={"X-Dealer-Id": "demo-dealer"})
    assert r.status_code == 200
    body = r.json()
    stage_keys = {s["key"] for s in body["stages"]}
    assert stage_keys == {
        "listings_surfaced",
        "leads_claimed",
        "leads_contacted",
        "leads_appointment",
        "leads_purchased",
    }
    assert all(s["count"] == 0 for s in body["stages"])


def test_funnel_counts_each_stage(client, db_session):
    now = datetime.now(timezone.utc)
    # Surface 3 listings
    listings = [
        _add_listing(db_session, external_id=f"l{i}", source="craigslist", first_seen_at=now)
        for i in range(3)
    ]
    # Claim 2 leads
    lead1 = _add_lead(db_session, listings[0].id)
    lead2 = _add_lead(db_session, listings[1].id)
    # Contact lead1 (outbound Interaction)
    db_session.add(
        Interaction(
            lead_id=lead1.id,
            kind="text",
            direction="outbound",
            body="hi",
            created_at=now,
        )
    )
    # Move lead2 to appointment
    lead2.status = "appointment"
    lead2.updated_at = now
    # Move lead1 to purchased
    lead1.status = "purchased"
    lead1.updated_at = now
    db_session.flush()

    r = client.get("/analytics/funnel", headers={"X-Dealer-Id": "demo-dealer"})
    body = r.json()
    counts = {s["key"]: s["count"] for s in body["stages"]}
    assert counts["listings_surfaced"] == 3
    assert counts["leads_claimed"] == 2
    assert counts["leads_contacted"] == 1
    assert counts["leads_appointment"] == 1
    assert counts["leads_purchased"] == 1


def test_funnel_dealer_isolation(client, db_session):
    now = datetime.now(timezone.utc)
    listing = _add_listing(db_session, external_id="iso-1", first_seen_at=now)
    # Lead belongs to a different dealer
    _add_lead(db_session, listing.id, dealer_id="other-dealer")

    r = client.get(
        "/analytics/funnel", headers={"X-Dealer-Id": "demo-dealer"}
    )
    counts = {s["key"]: s["count"] for s in r.json()["stages"]}
    # Listing still surfaced (global), but dealer's leads=0
    assert counts["listings_surfaced"] == 1
    assert counts["leads_claimed"] == 0


def test_funnel_sources_breakdown(client, db_session):
    now = datetime.now(timezone.utc)
    _add_listing(db_session, external_id="cl-1", source="craigslist", first_seen_at=now)
    _add_listing(db_session, external_id="cl-2", source="craigslist", first_seen_at=now)
    _add_listing(db_session, external_id="fb-1", source="facebook_marketplace", first_seen_at=now)
    fb_listing = _add_listing(
        db_session, external_id="fb-2", source="facebook_marketplace", first_seen_at=now
    )
    lead = _add_lead(db_session, fb_listing.id)
    lead.status = "purchased"
    lead.updated_at = now
    db_session.flush()

    r = client.get("/analytics/funnel", headers={"X-Dealer-Id": "demo-dealer"})
    body = r.json()
    by_source = {s["source"]: s for s in body["sources"]}
    assert by_source["craigslist"]["listings"] == 2
    assert by_source["facebook_marketplace"]["listings"] == 2
    assert by_source["facebook_marketplace"]["leads_purchased"] == 1


def test_funnel_respects_days_window(client, db_session):
    long_ago = datetime.now(timezone.utc) - timedelta(days=60)
    _add_listing(db_session, external_id="old", first_seen_at=long_ago)

    r = client.get(
        "/analytics/funnel",
        params={"days": 30},
        headers={"X-Dealer-Id": "demo-dealer"},
    )
    counts = {s["key"]: s["count"] for s in r.json()["stages"]}
    assert counts["listings_surfaced"] == 0

    r2 = client.get(
        "/analytics/funnel",
        params={"days": 90},
        headers={"X-Dealer-Id": "demo-dealer"},
    )
    counts2 = {s["key"]: s["count"] for s in r2.json()["stages"]}
    assert counts2["listings_surfaced"] == 1
