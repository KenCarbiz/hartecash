from fsbo.models import Listing


def test_rescore_computes_scores(client, db_session):
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
