from fsbo.models import Listing
from fsbo.templates.render import build_context, render


def test_render_replaces_tokens():
    listing = Listing(
        source="craigslist",
        external_id="x",
        url="http://x",
        year=2018,
        make="Ford",
        model="F-150",
        price=22000,
        mileage=85000,
        city="Tampa",
        state="FL",
    )
    ctx = build_context(listing)
    out = render("Hi — about your {{year}} {{make}} {{model}} in {{city}}?", ctx)
    assert out == "Hi — about your 2018 Ford F-150 in Tampa?"


def test_render_swallows_missing_tokens():
    listing = Listing(
        source="craigslist",
        external_id="x",
        url="http://x",
        year=2018,
        make="Ford",
        model="F-150",
    )
    ctx = build_context(listing)
    # {{trim}} and {{offer}} are empty; shouldn't leave placeholder text.
    out = render("{{year}} {{make}} {{trim}} {{model}} — offer {{offer}}", ctx)
    assert "{{" not in out
    assert "Ford" in out and "F-150" in out


def test_templates_autoseed(client):
    r = client.get("/templates", headers={"X-Dealer-Id": "dealer-1"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 9
    categories = {t["category"] for t in items}
    assert {"outreach", "vin_request", "offer"}.issubset(categories)


def test_templates_dealer_isolation(client):
    client.get("/templates", headers={"X-Dealer-Id": "dealer-a"})
    # Another dealer should get their own seeded set, not dealer-a's
    r = client.get("/templates", headers={"X-Dealer-Id": "dealer-b"})
    assert r.status_code == 200
    items = r.json()
    assert all(t["dealer_id"] == "dealer-b" for t in items)


def test_render_with_lead_offer(client, db_session):
    listing = Listing(
        source="craigslist",
        external_id="x",
        url="http://x",
        title="2018 Ford F-150",
        year=2018,
        make="Ford",
        model="F-150",
        price=22000,
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()

    lead_resp = client.post(
        "/leads",
        json={"listing_id": listing.id},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    lead_id = lead_resp.json()["id"]
    client.patch(
        f"/leads/{lead_id}",
        json={"offered_price": 18500},
        headers={"X-Dealer-Id": "dealer-1"},
    )

    templates = client.get("/templates?category=offer", headers={"X-Dealer-Id": "dealer-1"}).json()
    offer_tpl = next(t for t in templates if "{{offer}}" in t["body"])

    rendered = client.get(
        f"/templates/{offer_tpl['id']}/render/{listing.id}",
        headers={"X-Dealer-Id": "dealer-1"},
    ).json()
    assert "$18,500" in rendered["rendered"]
