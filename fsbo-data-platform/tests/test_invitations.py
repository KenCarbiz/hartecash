def _register_admin(client, email="admin@acme.com", dealer_name="Acme"):
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "supersecret123",
            "dealer_name": dealer_name,
        },
    )
    assert r.status_code == 201
    return r.json()


def test_admin_creates_invite(client):
    admin = _register_admin(client)
    r = client.post(
        "/invitations",
        json={"email": "teammate@acme.com"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["dealer_id"] == admin["dealer_id"]
    assert body["email"] == "teammate@acme.com"
    assert body["token"].startswith("inv_")
    assert "?token=" in body["accept_url_hint"]


def test_member_cannot_invite(client):
    _register_admin(client, email="admin1@acme.com", dealer_name="Acme")
    # Add a second user to the same dealer — they become a member
    reg2 = client.post(
        "/auth/register",
        json={
            "email": "member@acme.com",
            "password": "supersecret123",
            "dealer_slug": "acme",
        },
    )
    assert reg2.json()["role"] == "member"
    # member tries to invite — forbidden
    r = client.post(
        "/invitations",
        json={"email": "another@acme.com"},
    )
    assert r.status_code == 403


def test_invite_preview_without_auth(client):
    _register_admin(client)
    created = client.post(
        "/invitations",
        json={"email": "new@acme.com"},
    ).json()

    # Simulate a different browser with no session
    unauth = client.__class__(client.app)  # type: ignore[attr-defined]
    r = unauth.get("/invitations/preview", params={"token": created["token"]})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "new@acme.com"
    assert body["role"] == "member"
    assert body["dealer_id"] == created["dealer_id"]


def test_invite_accept_creates_user_and_logs_in(client):
    _register_admin(client)
    created = client.post(
        "/invitations",
        json={"email": "joiner@acme.com"},
    ).json()

    r = client.post(
        "/invitations/accept",
        json={
            "token": created["token"],
            "password": "newstrongpw123",
            "name": "Joiner",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "joiner@acme.com"
    assert body["dealer_id"] == created["dealer_id"]

    # Session cookie should now be set
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "joiner@acme.com"


def test_invite_accept_rejects_short_password(client):
    _register_admin(client)
    created = client.post(
        "/invitations",
        json={"email": "weakpw@acme.com"},
    ).json()
    r = client.post(
        "/invitations/accept",
        json={"token": created["token"], "password": "2short"},
    )
    assert r.status_code == 400


def test_invite_cannot_be_accepted_twice(client):
    _register_admin(client)
    created = client.post(
        "/invitations",
        json={"email": "once@acme.com"},
    ).json()
    client.post(
        "/invitations/accept",
        json={"token": created["token"], "password": "newstrongpw123"},
    )
    # Second accept fails
    r = client.post(
        "/invitations/accept",
        json={"token": created["token"], "password": "anotherpw123"},
    )
    assert r.status_code == 410


def test_admin_can_revoke(client):
    _register_admin(client)
    created = client.post(
        "/invitations",
        json={"email": "revoke@acme.com"},
    ).json()

    r = client.post(f"/invitations/{created['id']}/revoke")
    assert r.status_code == 200
    assert r.json()["revoked_at"] is not None

    # Revoked invites can't be previewed or accepted
    preview = client.get("/invitations/preview", params={"token": created["token"]})
    assert preview.status_code == 410


def test_admin_lists_invites(client):
    _register_admin(client)
    client.post("/invitations", json={"email": "a@acme.com"})
    client.post("/invitations", json={"email": "b@acme.com"})
    r = client.get("/invitations")
    assert r.status_code == 200
    emails = [x["email"] for x in r.json()]
    assert "a@acme.com" in emails
    assert "b@acme.com" in emails


def test_invite_unknown_token_404(client):
    _register_admin(client)
    r = client.get("/invitations/preview", params={"token": "inv_nope"})
    assert r.status_code == 404


def test_invite_email_already_exists(client):
    _register_admin(client, email="existing@acme.com")
    r = client.post(
        "/invitations",
        json={"email": "existing@acme.com"},
    )
    assert r.status_code == 409
