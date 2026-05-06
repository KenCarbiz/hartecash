"""Lead-routing config + least-loaded auto-assignment."""

from itertools import count

from fsbo.models import Dealer, Lead, Listing


_ext = count(1)


def _seed_dealer(db, slug="demo-dealer", mode="manual", pool=None):
    dealer = db.scalar(
        __import__("sqlalchemy").select(Dealer).where(Dealer.slug == slug)
    )
    if dealer is None:
        dealer = Dealer(slug=slug, name=f"{slug} co")
        db.add(dealer)
        db.flush()
    dealer.routing_mode = mode
    dealer.routing_pool = pool or []
    db.flush()
    return dealer


def _seed_listing(db) -> Listing:
    listing = Listing(
        source="craigslist",
        external_id=f"cl-{next(_ext)}",
        url="http://x",
        title="x",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    return listing


def test_get_routing_returns_default_when_no_dealer_row(client):
    body = client.get("/routing").json()
    assert body == {"mode": "manual", "pool": []}


def test_put_routing_persists_config(client, db_session):
    _seed_dealer(db_session)
    r = client.put(
        "/routing",
        json={"mode": "least_loaded", "pool": ["alice@x", "bob@x"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "least_loaded"
    assert body["pool"] == ["alice@x", "bob@x"]


def test_put_routing_dedupes_and_caps_pool(client, db_session):
    _seed_dealer(db_session)
    r = client.put(
        "/routing",
        json={
            "mode": "least_loaded",
            "pool": ["alice", "alice", "  ", "", "bob"],
        },
    )
    assert r.json()["pool"] == ["alice", "bob"]


def test_create_lead_with_explicit_assignee_skips_routing(client, db_session):
    _seed_dealer(db_session, mode="least_loaded", pool=["alice", "bob"])
    listing = _seed_listing(db_session)
    body = client.post(
        "/leads",
        json={"listing_id": listing.id, "assigned_to": "carol"},
    ).json()
    assert body["assigned_to"] == "carol"


def test_create_lead_least_loaded_assigns_to_lightest_rep(client, db_session):
    _seed_dealer(db_session, mode="least_loaded", pool=["alice", "bob"])

    # Pre-load alice with one active lead so bob is lighter.
    pre_listing = _seed_listing(db_session)
    db_session.add(
        Lead(
            dealer_id="demo-dealer",
            listing_id=pre_listing.id,
            assigned_to="alice",
            status="contacted",
        )
    )
    db_session.flush()

    new_listing = _seed_listing(db_session)
    body = client.post(
        "/leads", json={"listing_id": new_listing.id}
    ).json()
    assert body["assigned_to"] == "bob"


def test_create_lead_manual_mode_leaves_assigned_to_null(client, db_session):
    _seed_dealer(db_session, mode="manual", pool=["alice", "bob"])
    listing = _seed_listing(db_session)
    body = client.post("/leads", json={"listing_id": listing.id}).json()
    assert body["assigned_to"] is None


def test_bulk_claim_distributes_evenly(client, db_session):
    _seed_dealer(db_session, mode="least_loaded", pool=["alice", "bob", "carol"])
    listing_ids = []
    for _ in range(6):
        listing_ids.append(_seed_listing(db_session).id)

    body = client.post(
        "/leads/bulk-claim",
        json={"listing_ids": listing_ids},
    ).json()
    assert body["claimed"] == 6

    # Each rep should have exactly 2 of the 6 new leads.
    rows = db_session.scalars(
        __import__("sqlalchemy").select(Lead).where(
            Lead.dealer_id == "demo-dealer"
        )
    ).all()
    counts: dict[str | None, int] = {}
    for r in rows:
        counts[r.assigned_to] = counts.get(r.assigned_to, 0) + 1
    assert counts.get("alice") == 2
    assert counts.get("bob") == 2
    assert counts.get("carol") == 2


def test_bulk_claim_explicit_assignee_skips_routing(client, db_session):
    _seed_dealer(db_session, mode="least_loaded", pool=["alice", "bob"])
    listing_ids = [_seed_listing(db_session).id for _ in range(3)]
    body = client.post(
        "/leads/bulk-claim",
        json={"listing_ids": listing_ids, "assigned_to": "carol"},
    ).json()
    assert body["claimed"] == 3
    rows = db_session.scalars(
        __import__("sqlalchemy").select(Lead).where(Lead.dealer_id == "demo-dealer")
    ).all()
    assert all(r.assigned_to == "carol" for r in rows)


def test_routing_404s_for_unknown_dealer_on_put(client, db_session):
    """No Dealer row => can't persist (legacy demo paths predate Dealer)."""
    # Don't seed the demo-dealer Dealer row
    r = client.put("/routing", json={"mode": "manual", "pool": []})
    assert r.status_code == 404
