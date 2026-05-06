"""Webhook dispatch — dealer-scoped subscriptions + event fan-out.

Covers:
- Subscriptions are dealer-scoped on create + list + delete.
- Unknown event names rejected on create.
- lead.status_changed fires when /leads/{id}/status changes — but ONLY
  to subscriptions belonging to the lead's dealer (cross-dealer
  isolation).
- offer.accepted / offer.declined fire from the public seller endpoints.
- voice_call.completed fires from the Twilio status callback when
  CallStatus=completed (no fire on other statuses).
"""

from datetime import datetime, timedelta, timezone
from itertools import count

from sqlalchemy import select

from fsbo.models import (
    Lead,
    Listing,
    Offer,
    VoiceCall,
    WebhookDelivery,
    WebhookSubscription,
)


_ext = count(1)


def _seed_listing(db) -> Listing:
    listing = Listing(
        source="craigslist",
        external_id=f"cl-{next(_ext)}",
        url="http://x",
        title="2018 Honda Accord",
        seller_phone="(813) 555-0100",
        zip_code="33607",
        classification="private_seller",
    )
    db.add(listing)
    db.flush()
    return listing


def _seed_lead(db, dealer="demo-dealer", status="contacted") -> Lead:
    listing = _seed_listing(db)
    lead = Lead(dealer_id=dealer, listing_id=listing.id, status=status)
    db.add(lead)
    db.flush()
    return lead


def _make_sub(db, dealer_id: str, event: str, name: str = "demo") -> int:
    db.add(
        WebhookSubscription(
            dealer_id=dealer_id,
            name=name,
            url="https://example.com/hook",
            secret="s",
            event=event,
            active=True,
        )
    )
    db.flush()
    return db.scalar(
        select(WebhookSubscription.id)
        .where(
            WebhookSubscription.dealer_id == dealer_id,
            WebhookSubscription.event == event,
            WebhookSubscription.name == name,
        )
        .order_by(WebhookSubscription.id.desc())
        .limit(1)
    )


def test_create_subscription_persists_dealer_id(client):
    r = client.post(
        "/webhooks/subscriptions",
        json={
            "name": "DMS push",
            "url": "https://dealer.example.com/hook",
            "event": "lead.status_changed",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["dealer_id"] == "demo-dealer"
    assert body["secret"]


def test_create_subscription_rejects_unknown_event(client):
    r = client.post(
        "/webhooks/subscriptions",
        json={
            "name": "x",
            "url": "https://example.com/hook",
            "event": "not_a_real_event",
        },
    )
    assert r.status_code == 400
    assert "unknown event" in r.json()["detail"]


def test_list_subscriptions_is_dealer_scoped(client, db_session):
    _make_sub(db_session, "demo-dealer", "lead.status_changed", name="mine")
    _make_sub(db_session, "other-dealer", "lead.status_changed", name="theirs")
    rows = client.get("/webhooks/subscriptions").json()
    names = {r["name"] for r in rows}
    assert "mine" in names
    assert "theirs" not in names


def test_delete_subscription_404s_for_other_dealer(client, db_session):
    sub_id = _make_sub(db_session, "other-dealer", "lead.status_changed")
    r = client.delete(f"/webhooks/subscriptions/{sub_id}")
    assert r.status_code == 404


def test_events_endpoint_lists_supported_events(client):
    body = client.get("/webhooks/events").json()
    assert "listing.created" in body
    assert "lead.status_changed" in body
    assert "offer.accepted" in body
    assert "offer.declined" in body
    assert "voice_call.completed" in body


def test_lead_status_change_fires_dealer_scoped_webhook(client, db_session):
    lead = _seed_lead(db_session)
    sub_id = _make_sub(db_session, "demo-dealer", "lead.status_changed")
    # Other dealer also subscribed — should NOT receive
    other_sub_id = _make_sub(db_session, "other-dealer", "lead.status_changed")

    r = client.patch(f"/leads/{lead.id}", json={"status": "appointment"})
    assert r.status_code == 200

    deliveries = db_session.scalars(
        select(WebhookDelivery).where(WebhookDelivery.event == "lead.status_changed")
    ).all()
    sub_ids = {d.subscription_id for d in deliveries}
    assert sub_id in sub_ids
    assert other_sub_id not in sub_ids
    # Payload includes prev_status + new status
    payload = next(d.payload for d in deliveries if d.subscription_id == sub_id)
    assert payload["lead"]["prev_status"] == "contacted"
    assert payload["lead"]["status"] == "appointment"


def test_lead_status_unchanged_does_not_fire(client, db_session):
    lead = _seed_lead(db_session, status="contacted")
    _make_sub(db_session, "demo-dealer", "lead.status_changed")

    # Update something else; status stays the same
    client.patch(f"/leads/{lead.id}", json={"notes": "hello"})
    deliveries = db_session.scalars(
        select(WebhookDelivery).where(WebhookDelivery.event == "lead.status_changed")
    ).all()
    assert deliveries == []


def test_offer_accepted_fires_webhook(client, db_session):
    lead = _seed_lead(db_session)
    create = client.post(
        "/offers",
        json={"lead_id": lead.id, "amount_cents": 1850000},
    ).json()
    token = create["public_token"]
    _make_sub(db_session, "demo-dealer", "offer.accepted")

    # Public path — no auth
    client.cookies.clear()
    client.headers.pop("X-Dealer-Id", None)
    r = client.post(f"/offers/public/{token}/accept", json={"note": "tomorrow 10am"})
    assert r.status_code == 200

    deliveries = db_session.scalars(
        select(WebhookDelivery).where(WebhookDelivery.event == "offer.accepted")
    ).all()
    assert len(deliveries) == 1
    assert deliveries[0].payload["offer"]["status"] == "accepted"
    assert deliveries[0].payload["offer"]["seller_response_note"] == "tomorrow 10am"


def test_offer_declined_fires_webhook(client, db_session):
    lead = _seed_lead(db_session)
    create = client.post(
        "/offers", json={"lead_id": lead.id, "amount_cents": 1850000}
    ).json()
    token = create["public_token"]
    _make_sub(db_session, "demo-dealer", "offer.declined")

    client.cookies.clear()
    client.headers.pop("X-Dealer-Id", None)
    r = client.post(f"/offers/public/{token}/decline", json={"note": "too low"})
    assert r.status_code == 200

    deliveries = db_session.scalars(
        select(WebhookDelivery).where(WebhookDelivery.event == "offer.declined")
    ).all()
    assert len(deliveries) == 1


def test_voice_call_completed_fires_webhook(client, db_session):
    lead = _seed_lead(db_session)
    # Pre-create the VoiceCall row that the status callback updates.
    db_session.add(
        VoiceCall(
            lead_id=lead.id,
            dealer_id="demo-dealer",
            to_number="(813) 555-0100",
            status="in_progress",
        )
    )
    db_session.flush()
    call = db_session.scalar(select(VoiceCall))
    _make_sub(db_session, "demo-dealer", "voice_call.completed")

    r = client.post(
        f"/voice/twiml/status/{call.id}",
        data={"CallStatus": "completed", "CallDuration": "120"},
    )
    assert r.status_code == 200

    deliveries = db_session.scalars(
        select(WebhookDelivery).where(WebhookDelivery.event == "voice_call.completed")
    ).all()
    assert len(deliveries) == 1
    assert deliveries[0].payload["voice_call"]["duration_seconds"] == 120


def test_extension_ingest_fires_listing_created(client, db_session):
    """A FB Marketplace listing arriving via the extension fires
    listing.created to subscribed dealers. Auto-hidden listings
    (scams/curbstoners) don't fire — keeps DMS feeds clean."""
    db_session.add(
        WebhookSubscription(
            dealer_id="demo-dealer",
            name="hook",
            url="https://example.com/hook",
            secret="s",
            event="listing.created",
            active=True,
        )
    )
    db_session.flush()

    r = client.post(
        "/sources/extension/ingest",
        json={
            "listing": {
                "source": "facebook_marketplace",
                "external_id": "fb-listing-created-1",
                "url": "https://www.facebook.com/marketplace/item/1",
                "title": "2018 Honda Accord",
                "year": 2018,
                "make": "Honda",
                "model": "Accord",
                "price": 18500,
                "city": "Tampa",
                "state": "FL",
            }
        },
    )
    assert r.status_code == 200

    deliveries = db_session.scalars(
        select(WebhookDelivery).where(WebhookDelivery.event == "listing.created")
    ).all()
    assert len(deliveries) == 1


def test_voice_call_busy_does_not_fire(client, db_session):
    lead = _seed_lead(db_session)
    db_session.add(
        VoiceCall(
            lead_id=lead.id,
            dealer_id="demo-dealer",
            to_number="(813) 555-0100",
            status="in_progress",
        )
    )
    db_session.flush()
    call = db_session.scalar(select(VoiceCall))
    _make_sub(db_session, "demo-dealer", "voice_call.completed")

    r = client.post(
        f"/voice/twiml/status/{call.id}",
        data={"CallStatus": "busy", "CallDuration": "0"},
    )
    assert r.status_code == 200

    deliveries = db_session.scalars(
        select(WebhookDelivery).where(WebhookDelivery.event == "voice_call.completed")
    ).all()
    assert deliveries == []
