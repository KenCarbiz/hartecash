from fsbo.models import Lead, Listing


def _seed(db, external_id="ext-1", status="new", assigned_to=None):
    listing = Listing(
        source="facebook_marketplace",
        external_id=external_id,
        url="https://fb/item/1",
        title="2019 Ford F-150",
        year=2019,
        make="Ford",
        model="F-150",
        price=22000,
        mileage=38000,
        city="Tampa",
        state="FL",
        zip_code="33607",
        vin="1FTFW1ET5DFA12345",
        classification="private_seller",
        lead_quality_score=82,
    )
    db.add(listing)
    db.flush()
    lead = Lead(
        dealer_id="demo-dealer",
        listing_id=listing.id,
        status=status,
        assigned_to=assigned_to,
    )
    db.add(lead)
    db.flush()
    return lead


def test_export_csv_headers_and_content(client, db_session):
    _seed(db_session, external_id="a", status="contacted", assigned_to="alice")
    _seed(db_session, external_id="b", status="new")

    r = client.get("/leads/export.csv", headers={"X-Dealer-Id": "demo-dealer"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "autocurb_leads_" in r.headers["content-disposition"]

    body = r.text
    lines = body.strip().splitlines()
    assert lines[0].startswith("lead_id,status,assigned_to,")
    # Three rows (header + two leads)
    assert len(lines) == 3
    # Both external_ids + key fields appear somewhere
    assert "Ford" in body
    assert "F-150" in body
    assert "alice" in body
    assert "contacted" in body


def test_export_csv_dealer_isolation(client, db_session):
    listing = Listing(
        source="craigslist",
        external_id="other",
        url="http://x",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    db_session.add(
        Lead(dealer_id="other-dealer", listing_id=listing.id, status="new")
    )
    db_session.flush()

    # Request as demo-dealer → the "other-dealer" lead must not appear
    r = client.get("/leads/export.csv", headers={"X-Dealer-Id": "demo-dealer"})
    assert r.status_code == 200
    assert r.text.strip().count("\n") == 0  # just the header row


def test_export_csv_status_filter(client, db_session):
    _seed(db_session, external_id="c", status="contacted")
    _seed(db_session, external_id="d", status="new")

    r = client.get(
        "/leads/export.csv",
        params={"status": "contacted"},
        headers={"X-Dealer-Id": "demo-dealer"},
    )
    lines = r.text.strip().splitlines()
    assert len(lines) == 2  # header + 1 match
    assert "contacted" in lines[1]


def test_teammates_endpoint(client):
    client.post(
        "/auth/register",
        json={
            "email": "boss@acme.com",
            "password": "supersecret123",
            "dealer_name": "Acme",
        },
    )
    client.post(
        "/auth/register",
        json={
            "email": "helper@acme.com",
            "password": "supersecret123",
            "dealer_slug": "acme",
        },
    )
    r = client.get("/leads/teammates", headers={"X-Dealer-Id": "acme"})
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert {"boss@acme.com", "helper@acme.com"}.issubset(emails)


def test_teammates_dealer_isolation(client):
    client.post(
        "/auth/register",
        json={
            "email": "solo@example.com",
            "password": "supersecret123",
            "dealer_name": "Solo Co",
        },
    )
    r = client.get(
        "/leads/teammates", headers={"X-Dealer-Id": "demo-dealer"}
    )
    assert r.status_code == 200
    # demo-dealer has no users -> empty list
    assert r.json() == []
