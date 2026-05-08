"""Cross-lead activity log for managers.

GET /analytics/activity returns Interactions joined with their Lead +
Listing, scoped to the calling dealer. Powers the "who did what when"
manager-coaching view.
"""

from itertools import count

from fsbo.models import Interaction, Lead, Listing


_ext = count(1)


def _seed_lead(db, *, dealer="demo-dealer", title="2018 Honda Accord") -> Lead:
    listing = Listing(
        source="craigslist",
        external_id=f"cl-act-{next(_ext)}",
        url="http://x",
        title=title,
        seller_phone="(813) 555-0100",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    lead = Lead(dealer_id=dealer, listing_id=listing.id, status="new")
    db.add(lead)
    db.flush()
    return lead


def _seed_interaction(
    db, lead: Lead, *, kind="note", actor="rep@dealer.com", body="hi"
) -> Interaction:
    interaction = Interaction(
        lead_id=lead.id,
        kind=kind,
        actor=actor,
        body=body,
        direction="outbound" if kind in ("text", "email", "call") else None,
    )
    db.add(interaction)
    db.flush()
    return interaction


def test_empty_dealer_returns_no_rows(client, db_session):
    body = client.get("/analytics/activity").json()
    assert body["rows"] == []
    assert body["has_more"] is False


def test_returns_interactions_with_listing_title(client, db_session):
    lead = _seed_lead(db_session, title="2020 Toyota Tacoma")
    _seed_interaction(db_session, lead, kind="note", body="left vmail")

    body = client.get("/analytics/activity").json()
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["lead_id"] == lead.id
    assert row["listing_title"] == "2020 Toyota Tacoma"
    assert row["actor"] == "rep@dealer.com"
    assert row["kind"] == "note"
    assert row["body"] == "left vmail"


def test_actor_falls_back_to_assigned_to_when_interaction_actor_null(
    client, db_session
):
    lead = _seed_lead(db_session)
    lead.assigned_to = "fallback@dealer.com"
    db_session.add(
        Interaction(lead_id=lead.id, kind="note", actor=None, body="x")
    )
    db_session.flush()

    body = client.get("/analytics/activity").json()
    assert body["rows"][0]["actor"] == "fallback@dealer.com"


def test_ordering_is_newest_first(client, db_session):
    lead = _seed_lead(db_session)
    _seed_interaction(db_session, lead, body="first")
    _seed_interaction(db_session, lead, body="second")

    body = client.get("/analytics/activity").json()
    bodies = [r["body"] for r in body["rows"]]
    assert bodies == ["second", "first"]


def test_kind_filter(client, db_session):
    lead = _seed_lead(db_session)
    _seed_interaction(db_session, lead, kind="note")
    _seed_interaction(db_session, lead, kind="text")
    _seed_interaction(db_session, lead, kind="text")

    body = client.get("/analytics/activity?kind=text").json()
    assert len(body["rows"]) == 2
    assert {r["kind"] for r in body["rows"]} == {"text"}


def test_actor_filter(client, db_session):
    lead = _seed_lead(db_session)
    _seed_interaction(db_session, lead, actor="alice@dealer.com")
    _seed_interaction(db_session, lead, actor="bob@dealer.com")

    body = client.get("/analytics/activity?actor=alice@dealer.com").json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["actor"] == "alice@dealer.com"


def test_pagination_has_more_flag(client, db_session):
    lead = _seed_lead(db_session)
    for i in range(5):
        _seed_interaction(db_session, lead, body=f"row{i}")

    body = client.get("/analytics/activity?limit=2").json()
    assert len(body["rows"]) == 2
    assert body["has_more"] is True

    body = client.get("/analytics/activity?limit=10").json()
    assert len(body["rows"]) == 5
    assert body["has_more"] is False


def test_offset_pages_correctly(client, db_session):
    lead = _seed_lead(db_session)
    for i in range(4):
        _seed_interaction(db_session, lead, body=f"row{i}")

    page1 = client.get("/analytics/activity?limit=2&offset=0").json()
    page2 = client.get("/analytics/activity?limit=2&offset=2").json()

    ids1 = [r["interaction_id"] for r in page1["rows"]]
    ids2 = [r["interaction_id"] for r in page2["rows"]]
    assert set(ids1).isdisjoint(set(ids2))
    assert len(ids1) == 2
    assert len(ids2) == 2


def test_activity_is_dealer_scoped(client, db_session):
    mine = _seed_lead(db_session, dealer="demo-dealer")
    other = _seed_lead(db_session, dealer="other-dealer")
    _seed_interaction(db_session, mine, body="mine")
    _seed_interaction(db_session, other, body="theirs")

    body = client.get("/analytics/activity").json()
    bodies = [r["body"] for r in body["rows"]]
    assert "mine" in bodies
    assert "theirs" not in bodies
