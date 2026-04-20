from fsbo.enrichment.price_tracking import count_drops, record_price
from fsbo.models import Listing


def _listing(db, price=20000):
    row = Listing(
        source="craigslist",
        external_id="cl-1",
        url="http://x",
        title="2018 Ford F-150",
        price=price,
        classification="private_seller",
    )
    db.add(row)
    db.flush()
    return row


def test_initial_record(db_session):
    listing = _listing(db_session)
    assert record_price(db_session, listing, 20000)
    assert count_drops(db_session, listing.id) == 0


def test_unchanged_price_no_row(db_session):
    listing = _listing(db_session)
    record_price(db_session, listing, 20000)
    assert not record_price(db_session, listing, 20000)


def test_price_drop_counted(db_session):
    listing = _listing(db_session)
    record_price(db_session, listing, 20000)
    record_price(db_session, listing, 18500)
    assert count_drops(db_session, listing.id) == 1


def test_multiple_drops(db_session):
    listing = _listing(db_session)
    record_price(db_session, listing, 20000)
    record_price(db_session, listing, 19000)
    record_price(db_session, listing, 18000)
    record_price(db_session, listing, 17500)
    assert count_drops(db_session, listing.id) == 3


def test_increase_not_counted_as_drop(db_session):
    listing = _listing(db_session)
    record_price(db_session, listing, 20000)
    record_price(db_session, listing, 22000)  # owner increased price
    assert count_drops(db_session, listing.id) == 0


def test_stats_endpoint(client, db_session):
    listing = _listing(db_session)
    record_price(db_session, listing, 20000)
    record_price(db_session, listing, 18500)

    r = client.get(f"/listings/{listing.id}/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["price_drops"] == 1
    assert abs(body["total_drop_amount"] - 1500) < 1
    assert len(body["price_history"]) == 2
