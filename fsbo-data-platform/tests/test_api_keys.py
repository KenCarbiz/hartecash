from sqlalchemy import select

from fsbo.api.routes.api_keys import resolve_dealer_from_token
from fsbo.models import ApiKey


def test_create_and_list_and_revoke(client, db_session):
    create = client.post(
        "/api-keys",
        json={"name": "chrome-ext-dealer-1"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    assert create.status_code == 201
    body = create.json()
    token = body["token"]
    assert token.startswith("ac_live_")
    assert body["token_prefix"].startswith("ac_live_")

    listed = client.get("/api-keys", headers={"X-Dealer-Id": "dealer-1"}).json()
    assert len(listed) == 1
    assert listed[0]["name"] == "chrome-ext-dealer-1"

    # Dealer isolation
    other = client.get("/api-keys", headers={"X-Dealer-Id": "dealer-2"}).json()
    assert other == []

    revoked = client.post(
        f"/api-keys/{listed[0]['id']}/revoke",
        headers={"X-Dealer-Id": "dealer-1"},
    ).json()
    assert revoked["revoked_at"] is not None


def test_resolve_dealer_from_token(client, db_session):
    create = client.post(
        "/api-keys",
        json={"name": "test-key"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    token = create.json()["token"]

    resolved = resolve_dealer_from_token(db_session, token)
    assert resolved == "dealer-1"

    unknown = resolve_dealer_from_token(db_session, "ac_live_doesnt_exist")
    assert unknown is None


def test_revoked_token_stops_resolving(client, db_session):
    create = client.post(
        "/api-keys",
        json={"name": "test-key"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    token = create.json()["token"]
    key_id = create.json()["id"]

    client.post(f"/api-keys/{key_id}/revoke", headers={"X-Dealer-Id": "dealer-1"})

    resolved = resolve_dealer_from_token(db_session, token)
    assert resolved is None


def test_cross_dealer_revoke_forbidden(client, db_session):
    create = client.post(
        "/api-keys",
        json={"name": "test-key"},
        headers={"X-Dealer-Id": "dealer-1"},
    )
    key_id = create.json()["id"]

    r = client.post(f"/api-keys/{key_id}/revoke", headers={"X-Dealer-Id": "dealer-2"})
    assert r.status_code == 404

    # Still not revoked
    key = db_session.scalar(select(ApiKey).where(ApiKey.id == key_id))
    assert key.revoked_at is None
