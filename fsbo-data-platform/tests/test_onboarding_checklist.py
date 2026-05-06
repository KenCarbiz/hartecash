"""First-run onboarding checklist.

GET /onboarding/checklist returns a list of setup steps + done flags
the dashboard renders as a progress bar. Each item is independently
toggled by a real signal (Twilio configured, team member invited,
routing pool set, etc.) — no per-dealer "skipped" flag.
"""

from itertools import count

from fsbo.models import (
    ApiKey,
    Dealer,
    Lead,
    Listing,
    SavedSearch,
    Subscription,
    User,
    WebhookSubscription,
)


_ext = count(1)


def _seed_dealer(db, slug="demo-dealer", **overrides) -> Dealer:
    base = dict(slug=slug, name=slug.title())
    base.update(overrides)
    dealer = Dealer(**base)
    db.add(dealer)
    db.flush()
    return dealer


def test_empty_dealer_has_zero_completed(client, db_session):
    _seed_dealer(db_session)
    r = client.get("/onboarding/checklist")
    assert r.status_code == 200
    body = r.json()
    assert body["dealer_id"] == "demo-dealer"
    assert body["completed"] == 0
    assert body["total"] == len(body["items"])
    keys = {i["key"] for i in body["items"]}
    # All the expected steps present
    assert keys == {
        "twilio",
        "team_member",
        "routing",
        "extension",
        "saved_search",
        "first_lead",
        "webhook",
        "subscription",
    }


def test_routing_done_when_pool_configured(client, db_session):
    _seed_dealer(
        db_session,
        routing_mode="least_loaded",
        routing_pool=["rep1@dealer.com"],
    )
    body = client.get("/onboarding/checklist").json()
    routing = next(i for i in body["items"] if i["key"] == "routing")
    assert routing["done"] is True
    assert body["completed"] >= 1


def test_routing_not_done_when_mode_manual(client, db_session):
    _seed_dealer(
        db_session, routing_mode="manual", routing_pool=["rep1@dealer.com"]
    )
    body = client.get("/onboarding/checklist").json()
    routing = next(i for i in body["items"] if i["key"] == "routing")
    assert routing["done"] is False


def test_team_member_done_when_two_active_users(client, db_session):
    _seed_dealer(db_session)
    db_session.add_all(
        [
            User(
                email="owner@dealer.com",
                password_hash="x",
                dealer_id="demo-dealer",
                role="admin",
                is_active=True,
            ),
            User(
                email="rep@dealer.com",
                password_hash="x",
                dealer_id="demo-dealer",
                role="member",
                is_active=True,
            ),
        ]
    )
    db_session.flush()
    body = client.get("/onboarding/checklist").json()
    item = next(i for i in body["items"] if i["key"] == "team_member")
    assert item["done"] is True


def test_team_member_not_done_for_solo_owner(client, db_session):
    _seed_dealer(db_session)
    db_session.add(
        User(
            email="solo@dealer.com",
            password_hash="x",
            dealer_id="demo-dealer",
            role="admin",
            is_active=True,
        )
    )
    db_session.flush()
    body = client.get("/onboarding/checklist").json()
    item = next(i for i in body["items"] if i["key"] == "team_member")
    assert item["done"] is False


def test_extension_done_when_api_key_exists(client, db_session):
    _seed_dealer(db_session)
    db_session.add(
        ApiKey(
            dealer_id="demo-dealer",
            name="Extension",
            token_hash="h" * 64,
            token_prefix="ac_live_x",
        )
    )
    db_session.flush()
    body = client.get("/onboarding/checklist").json()
    item = next(i for i in body["items"] if i["key"] == "extension")
    assert item["done"] is True


def test_first_lead_done_when_any_lead_claimed(client, db_session):
    _seed_dealer(db_session)
    listing = Listing(
        source="craigslist",
        external_id=f"cl-onb-{next(_ext)}",
        url="http://x",
        title="x",
        seller_phone="(813) 555-0100",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    db_session.add(
        Lead(dealer_id="demo-dealer", listing_id=listing.id, status="new")
    )
    db_session.flush()
    body = client.get("/onboarding/checklist").json()
    item = next(i for i in body["items"] if i["key"] == "first_lead")
    assert item["done"] is True


def test_saved_search_done_when_one_exists(client, db_session):
    _seed_dealer(db_session)
    db_session.add(
        SavedSearch(
            dealer_id="demo-dealer",
            name="Tampa Hondas",
            query={"make": "Honda"},
        )
    )
    db_session.flush()
    body = client.get("/onboarding/checklist").json()
    item = next(i for i in body["items"] if i["key"] == "saved_search")
    assert item["done"] is True


def test_subscription_done_only_for_active_or_trialing(client, db_session):
    _seed_dealer(db_session)
    db_session.add(
        Subscription(
            dealer_id="demo-dealer",
            stripe_subscription_id="sub_x",
            stripe_customer_id="cus_x",
            status="canceled",
            plan="starter",
        )
    )
    db_session.flush()
    body = client.get("/onboarding/checklist").json()
    item = next(i for i in body["items"] if i["key"] == "subscription")
    assert item["done"] is False

    # Flip to active → done flips true
    from sqlalchemy import select as _select

    sub = db_session.scalar(
        _select(Subscription).where(Subscription.dealer_id == "demo-dealer")
    )
    sub.status = "active"
    db_session.flush()
    body = client.get("/onboarding/checklist").json()
    item = next(i for i in body["items"] if i["key"] == "subscription")
    assert item["done"] is True


def test_webhook_done_when_active_sub_exists(client, db_session):
    _seed_dealer(db_session)
    db_session.add(
        WebhookSubscription(
            dealer_id="demo-dealer",
            name="DMS",
            url="https://example.com/hook",
            secret="s",
            event="lead.status_changed",
            active=True,
        )
    )
    db_session.flush()
    body = client.get("/onboarding/checklist").json()
    item = next(i for i in body["items"] if i["key"] == "webhook")
    assert item["done"] is True


def test_checklist_is_dealer_scoped(client, db_session):
    """Other dealer's signals don't bleed into mine."""
    _seed_dealer(db_session, slug="demo-dealer")
    _seed_dealer(db_session, slug="other-dealer")
    listing = Listing(
        source="craigslist",
        external_id=f"cl-onb-{next(_ext)}",
        url="http://x",
        title="x",
        seller_phone="(813) 555-0101",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    # other-dealer claimed a lead — must not flip my checklist
    db_session.add(
        Lead(dealer_id="other-dealer", listing_id=listing.id, status="new")
    )
    db_session.flush()
    body = client.get("/onboarding/checklist").json()
    item = next(i for i in body["items"] if i["key"] == "first_lead")
    assert item["done"] is False
