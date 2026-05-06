from fsbo.models import Listing


def _login_as_admin(client):
    """Register the first user at a dealer (auto-promoted to admin) and
    return the resulting authenticated client."""
    client.post(
        "/auth/register",
        json={
            "email": "boss@admin-test.com",
            "password": "supersecret123",
            "dealer_name": "Admin Co",
        },
    )
    return client


def test_rescore_computes_scores(client, db_session):
    _login_as_admin(client)
    # Listings without quality scores
    for i in range(3):
        db_session.add(
            Listing(
                source="craigslist",
                external_id=f"cl-{i}",
                url=f"http://x/{i}",
                title=f"2019 Ford F-150 #{i}",
                year=2019,
                make="Ford",
                model="F-150",
                price=22000 + i * 500,
                classification="private_seller",
                images=["a.jpg", "b.jpg"],
            )
        )
    db_session.flush()

    r = client.post("/admin/rescore")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["updated"] == 3

    listings = db_session.query(Listing).all()
    assert all(listing.lead_quality_score is not None for listing in listings)
    assert all(listing.quality_breakdown for listing in listings)


def test_rescore_rejects_non_admin(client, db_session):
    """Second user at the same dealer is auto-assigned member role."""
    client.post(
        "/auth/register",
        json={
            "email": "boss@admin-test.com",
            "password": "supersecret123",
            "dealer_name": "Admin Co",
        },
    )
    # log out first user, register second
    client.post("/auth/logout")
    client.post(
        "/auth/register",
        json={
            "email": "member@admin-test.com",
            "password": "supersecret123",
            "dealer_slug": "admin-co",
        },
    )
    r = client.post("/admin/rescore")
    assert r.status_code == 403


def test_rescore_rejects_no_session(client):
    client.cookies.clear()
    client.headers.pop("X-Dealer-Id", None)
    r = client.post("/admin/rescore")
    assert r.status_code == 401
