from fsbo.auth.password import hash_password, verify_password
from fsbo.auth.tokens import SESSION_COOKIE_NAME, issue, verify
from fsbo.models import Dealer, User


def test_hash_and_verify_password():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)
    assert not verify_password("", h)


def test_jwt_roundtrip():
    token = issue(user_id=42, dealer_id="ac-test", email="alice@test")
    claims = verify(token)
    assert claims is not None
    assert claims["sub"] == "42"
    assert claims["dealer_id"] == "ac-test"
    assert claims["email"] == "alice@test"


def test_jwt_rejects_tampered():
    token = issue(42, "ac-test", "alice@test")
    tampered = token[:-5] + "XXXXX"
    assert verify(tampered) is None
    assert verify("") is None


def test_register_creates_dealer_and_admin_user(client, db_session):
    r = client.post(
        "/auth/register",
        json={
            "email": "founder@example.com",
            "password": "supersecret123",
            "name": "Founder",
            "dealer_name": "Example Motors",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "founder@example.com"
    assert body["role"] == "admin"
    assert body["dealer_id"]  # slug derived from dealer_name

    # Dealer row created
    dealer = db_session.query(Dealer).filter_by(slug=body["dealer_id"]).first()
    assert dealer is not None
    # User row created
    user = db_session.query(User).filter_by(email="founder@example.com").first()
    assert user is not None
    # Session cookie set
    assert SESSION_COOKIE_NAME in r.cookies


def test_register_duplicate_email(client):
    client.post(
        "/auth/register",
        json={
            "email": "dupe@example.com",
            "password": "supersecret123",
            "dealer_name": "Dupe Co",
        },
    )
    r = client.post(
        "/auth/register",
        json={
            "email": "dupe@example.com",
            "password": "supersecret123",
            "dealer_name": "Dupe Co Two",
        },
    )
    assert r.status_code == 409


def test_second_user_at_dealer_is_member(client):
    client.post(
        "/auth/register",
        json={
            "email": "admin@dealer.com",
            "password": "supersecret123",
            "dealer_slug": "shared-dealer",
        },
    )
    r = client.post(
        "/auth/register",
        json={
            "email": "member@dealer.com",
            "password": "supersecret123",
            "dealer_slug": "shared-dealer",
        },
    )
    assert r.status_code == 201
    assert r.json()["role"] == "member"
    assert r.json()["dealer_id"] == "shared-dealer"


def test_login_success_sets_cookie(client):
    client.post(
        "/auth/register",
        json={
            "email": "alice@acme.com",
            "password": "correcthorse",
            "dealer_name": "Acme",
        },
    )
    r = client.post(
        "/auth/login",
        json={"email": "alice@acme.com", "password": "correcthorse"},
    )
    assert r.status_code == 200
    assert SESSION_COOKIE_NAME in r.cookies
    assert r.json()["email"] == "alice@acme.com"


def test_login_wrong_password(client):
    client.post(
        "/auth/register",
        json={
            "email": "bob@acme.com",
            "password": "correcthorse",
            "dealer_name": "Acme",
        },
    )
    r = client.post(
        "/auth/login",
        json={"email": "bob@acme.com", "password": "wrong"},
    )
    assert r.status_code == 401


def test_me_returns_authenticated_user(client):
    client.post(
        "/auth/register",
        json={
            "email": "me@acme.com",
            "password": "correcthorse",
            "dealer_name": "Acme",
        },
    )
    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "me@acme.com"


def test_me_unauthenticated(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_logout_clears_cookie(client):
    client.post(
        "/auth/register",
        json={
            "email": "logout@acme.com",
            "password": "correcthorse",
            "dealer_name": "Acme",
        },
    )
    r = client.post("/auth/logout")
    assert r.status_code == 204
    # After logout, /me should be unauthenticated
    me = client.get("/auth/me")
    assert me.status_code == 401


def test_api_key_token_resolves_dealer(client):
    # Register + create an API key, then use the key on a new session
    reg = client.post(
        "/auth/register",
        json={
            "email": "keys@acme.com",
            "password": "correcthorse",
            "dealer_name": "Keys Co",
        },
    )
    dealer_id = reg.json()["dealer_id"]

    key_resp = client.post(
        "/api-keys",
        json={"name": "extension"},
        headers={"X-Dealer-Id": dealer_id},
    )
    token = key_resp.json()["token"]

    # Use bearer token to hit /api-keys again (resolver should accept it)
    listed = client.get("/api-keys", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
