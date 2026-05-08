"""Dealership-level first-response SLA stats.

GET /analytics/sla aggregates Lead.first_responded_at across the
dealer's leads in the last N days. Median + p90 are the manager-level
metrics; the % buckets are industry benchmarks (5 / 30 / 120 minutes).
"""

from datetime import datetime, timedelta, timezone
from itertools import count

from fsbo.crm.response import mark_first_response
from fsbo.models import Lead, Listing


_ext = count(1)


def _seed_listing(db) -> Listing:
    listing = Listing(
        source="craigslist",
        external_id=f"cl-sla-{next(_ext)}",
        url="http://x",
        title="x",
        seller_phone="(813) 555-0100",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    return listing


def _seed_lead(
    db,
    *,
    dealer="demo-dealer",
    created_minutes_ago=60,
    response_minutes_after_create: float | None = None,
    deleted: bool = False,
) -> Lead:
    listing = _seed_listing(db)
    created = datetime.now(timezone.utc) - timedelta(minutes=created_minutes_ago)
    lead = Lead(
        dealer_id=dealer,
        listing_id=listing.id,
        status="new",
        created_at=created,
        updated_at=created,
    )
    if response_minutes_after_create is not None:
        lead.first_responded_at = created + timedelta(
            minutes=response_minutes_after_create
        )
    if deleted:
        lead.deleted_at = datetime.now(timezone.utc)
    db.add(lead)
    db.flush()
    return lead


def test_empty_dealer_returns_zeros(client, db_session):
    body = client.get("/analytics/sla").json()
    assert body["leads_total"] == 0
    assert body["leads_responded"] == 0
    assert body["median_response_minutes"] is None
    assert body["p90_response_minutes"] is None
    assert body["avg_response_minutes"] is None
    assert body["pct_under_5_min"] == 0.0


def test_responded_leads_compute_median_and_pcts(client, db_session):
    # Five responses: 1m, 3m, 7m, 20m, 60m
    for r in [1, 3, 7, 20, 60]:
        _seed_lead(
            db_session, created_minutes_ago=120, response_minutes_after_create=r
        )

    body = client.get("/analytics/sla").json()
    assert body["leads_total"] == 5
    assert body["leads_responded"] == 5
    assert body["leads_unresponded"] == 0
    # 5 sorted [1,3,7,20,60] — nearest-rank median (50%) = index 2 (= 7m)
    assert body["median_response_minutes"] == 7.0
    # p90 nearest-rank = ceil(0.9*5)=5 → index 4 = 60
    assert body["p90_response_minutes"] == 60.0
    assert body["avg_response_minutes"] == round((1 + 3 + 7 + 20 + 60) / 5, 1)
    # 2 of 5 under 5min = 40%
    assert body["pct_under_5_min"] == 40.0
    # 4 of 5 under 30min = 80%
    assert body["pct_under_30_min"] == 80.0
    assert body["pct_under_2_hr"] == 100.0


def test_breach_count_includes_old_unresponded_and_late_responses(
    client, db_session
):
    # In-SLA: responded in 2m
    _seed_lead(
        db_session, created_minutes_ago=120, response_minutes_after_create=2
    )
    # Breach: responded in 30m (sla=5)
    _seed_lead(
        db_session, created_minutes_ago=120, response_minutes_after_create=30
    )
    # Breach: never responded, old enough to count
    _seed_lead(db_session, created_minutes_ago=120)
    # Pending (fresh): never responded, inside SLA window
    _seed_lead(db_session, created_minutes_ago=2)

    body = client.get("/analytics/sla?sla_minutes=5").json()
    assert body["leads_total"] == 4
    assert body["leads_responded"] == 2
    assert body["leads_unresponded"] == 2  # old + fresh
    assert body["leads_within_sla"] == 1
    # Breached: late response (30m > 5m) + old unresponded
    assert body["leads_breached"] == 2


def test_sla_window_filter_excludes_old_leads(client, db_session):
    """Lead older than the days window must not appear."""
    # 90 days ago
    _seed_lead(
        db_session,
        created_minutes_ago=90 * 24 * 60,
        response_minutes_after_create=1,
    )
    # 5 days ago
    _seed_lead(
        db_session,
        created_minutes_ago=5 * 24 * 60,
        response_minutes_after_create=1,
    )

    body = client.get("/analytics/sla?days=30").json()
    assert body["leads_total"] == 1


def test_archived_leads_are_excluded(client, db_session):
    _seed_lead(
        db_session,
        created_minutes_ago=120,
        response_minutes_after_create=1,
    )
    _seed_lead(
        db_session,
        created_minutes_ago=120,
        response_minutes_after_create=1,
        deleted=True,
    )

    body = client.get("/analytics/sla").json()
    assert body["leads_total"] == 1


def test_sla_is_dealer_scoped(client, db_session):
    _seed_lead(db_session, dealer="demo-dealer", response_minutes_after_create=1)
    _seed_lead(
        db_session, dealer="other-dealer", response_minutes_after_create=999
    )

    body = client.get("/analytics/sla").json()
    assert body["leads_total"] == 1
    assert body["median_response_minutes"] == 1.0


def test_helper_marks_first_response_for_sla(client, db_session):
    """The mark_first_response helper drives the SLA pipeline; sanity-
    check the integration: stamping via helper makes the lead show up
    as responded in /analytics/sla."""
    listing = _seed_listing(db_session)
    lead = Lead(
        dealer_id="demo-dealer",
        listing_id=listing.id,
        status="new",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(lead)
    db_session.flush()

    body = client.get("/analytics/sla").json()
    assert body["leads_responded"] == 0

    mark_first_response(lead)
    db_session.flush()

    body = client.get("/analytics/sla").json()
    assert body["leads_responded"] == 1
