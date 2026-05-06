"""Multi-rooftop dealer groups + group-funnel rollup."""

from datetime import datetime, timedelta, timezone
from itertools import count

from sqlalchemy import select

from fsbo.models import Dealer, DealerGroup, Lead, Listing


_ext = count(1)


def _ensure_dealer(db, slug: str) -> Dealer:
    dealer = db.scalar(select(Dealer).where(Dealer.slug == slug))
    if dealer is None:
        dealer = Dealer(slug=slug, name=f"{slug.title()} Co")
        db.add(dealer)
        db.flush()
    return dealer


def _seed_lead(db, dealer_slug: str, status: str = "new") -> Lead:
    listing = Listing(
        source="craigslist",
        external_id=f"cl-{next(_ext)}",
        url="http://x",
        title="2018 Honda Accord",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    lead = Lead(dealer_id=dealer_slug, listing_id=listing.id, status=status)
    db.add(lead)
    db.flush()
    return lead


def test_create_group_auto_joins_creator(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    r = client.post("/groups", json={"name": "Acme Auto Group", "slug": "acme"})
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == "acme"
    assert body["owner_dealer_id"] == "demo-dealer"
    assert body["member_dealer_slugs"] == ["demo-dealer"]


def test_get_my_group_returns_null_when_unaffiliated(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    body = client.get("/groups/me").json()
    assert body is None


def test_get_my_group_returns_membership(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    client.post("/groups", json={"name": "Acme", "slug": "acme"})
    body = client.get("/groups/me").json()
    assert body is not None
    assert body["slug"] == "acme"


def test_create_rejects_invalid_slug(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    r = client.post("/groups", json={"name": "x", "slug": "BAD SLUG"})
    assert r.status_code == 400


def test_create_rejects_duplicate_slug(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    _ensure_dealer(db_session, "second")
    client.post("/groups", json={"name": "Acme", "slug": "acme"})
    # Switch to a second dealer's identity
    r = client.post(
        "/groups",
        json={"name": "Other Acme", "slug": "acme"},
        headers={"X-Dealer-Id": "second"},
    )
    assert r.status_code == 409


def test_create_rejects_when_dealer_already_in_group(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    client.post("/groups", json={"name": "Acme", "slug": "acme"})
    r = client.post("/groups", json={"name": "Other", "slug": "other"})
    assert r.status_code == 409


def test_owner_can_add_and_remove_members(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    _ensure_dealer(db_session, "tampa")
    _ensure_dealer(db_session, "orlando")

    client.post("/groups", json={"name": "Acme", "slug": "acme"})

    # Owner adds members
    r = client.post(
        "/groups/acme/dealers", json={"dealer_slug": "tampa"}
    )
    assert r.status_code == 200
    assert "tampa" in r.json()["member_dealer_slugs"]
    r = client.post(
        "/groups/acme/dealers", json={"dealer_slug": "orlando"}
    )
    assert "orlando" in r.json()["member_dealer_slugs"]

    # Owner removes one
    r = client.delete("/groups/acme/dealers/tampa")
    assert r.status_code == 200
    assert "tampa" not in r.json()["member_dealer_slugs"]


def test_non_owner_cannot_manage_membership(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    _ensure_dealer(db_session, "tampa")

    client.post("/groups", json={"name": "Acme", "slug": "acme"})
    # tampa tries to add itself
    r = client.post(
        "/groups/acme/dealers",
        json={"dealer_slug": "tampa"},
        headers={"X-Dealer-Id": "tampa"},
    )
    assert r.status_code == 403


def test_cannot_remove_owner(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    client.post("/groups", json={"name": "Acme", "slug": "acme"})
    r = client.delete("/groups/acme/dealers/demo-dealer")
    assert r.status_code == 409


def test_cannot_add_dealer_already_in_another_group(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    _ensure_dealer(db_session, "tampa")

    # demo creates Acme; tampa creates its own group
    client.post("/groups", json={"name": "Acme", "slug": "acme"})
    client.post(
        "/groups",
        json={"name": "Other", "slug": "other"},
        headers={"X-Dealer-Id": "tampa"},
    )
    # demo tries to pull tampa into Acme
    r = client.post(
        "/groups/acme/dealers", json={"dealer_slug": "tampa"}
    )
    assert r.status_code == 409


def test_group_funnel_rolls_up_member_dealers(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    _ensure_dealer(db_session, "tampa")
    _ensure_dealer(db_session, "orlando")

    client.post("/groups", json={"name": "Acme", "slug": "acme"})
    client.post("/groups/acme/dealers", json={"dealer_slug": "tampa"})
    client.post("/groups/acme/dealers", json={"dealer_slug": "orlando"})

    # Seed: 2 demo leads (1 purchased), 1 tampa (appointment), 0 orlando
    _seed_lead(db_session, "demo-dealer", status="purchased")
    _seed_lead(db_session, "demo-dealer", status="contacted")
    _seed_lead(db_session, "tampa", status="appointment")

    body = client.get("/analytics/group-funnel").json()
    assert body["group_slug"] == "acme"
    rooftop_ids = {r["dealer_id"] for r in body["rooftops"]}
    assert rooftop_ids == {"demo-dealer", "tampa", "orlando"}
    totals = body["totals"]
    assert totals["leads_claimed"] == 3
    assert totals["leads_purchased"] == 1
    assert totals["leads_appointment"] == 1


def test_group_funnel_404s_when_dealer_has_no_group(client, db_session):
    _ensure_dealer(db_session, "demo-dealer")
    r = client.get("/analytics/group-funnel")
    assert r.status_code == 404
