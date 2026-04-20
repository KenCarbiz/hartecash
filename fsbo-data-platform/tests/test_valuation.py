from fsbo.models import Listing
from fsbo.valuation.market import estimate


def _seed_comps(db, count=10, price_start=18000, year=2018):
    for i in range(count):
        db.add(
            Listing(
                source="craigslist",
                external_id=f"cl-{i}",
                url=f"http://x/{i}",
                title=f"{year} Ford F-150 comp {i}",
                year=year,
                make="Ford",
                model="F-150",
                mileage=85000 + i * 1000,
                price=price_start + i * 500,
                classification="private_seller",
            )
        )
    db.flush()


def test_estimate_with_comps(db_session):
    _seed_comps(db_session, count=10)
    target = Listing(
        source="craigslist",
        external_id="target",
        url="http://x/t",
        title="2018 Ford F-150 target",
        year=2018,
        make="Ford",
        model="F-150",
        mileage=85000,
        price=20000,
        classification="private_seller",
    )
    db_session.add(target)
    db_session.flush()

    est = estimate(db_session, target)
    assert est.sample_size == 10
    assert est.median is not None
    assert est.p25 is not None and est.p75 is not None
    assert est.p25 <= est.median <= est.p75


def test_verdict_above(db_session):
    # Comps 18-22.5k, target 28k -> above
    _seed_comps(db_session, count=10)
    target = Listing(
        source="craigslist",
        external_id="target",
        url="http://x/t",
        year=2018,
        make="Ford",
        model="F-150",
        mileage=85000,
        price=28000,
        classification="private_seller",
    )
    db_session.add(target)
    db_session.flush()
    est = estimate(db_session, target)
    assert est.verdict == "above"
    assert est.delta_pct is not None and est.delta_pct > 20


def test_verdict_below(db_session):
    _seed_comps(db_session, count=10)
    target = Listing(
        source="craigslist",
        external_id="target",
        url="http://x/t",
        year=2018,
        make="Ford",
        model="F-150",
        mileage=85000,
        price=15000,
        classification="private_seller",
    )
    db_session.add(target)
    db_session.flush()
    est = estimate(db_session, target)
    assert est.verdict == "below"


def test_no_comps_returns_unknown(db_session):
    target = Listing(
        source="craigslist",
        external_id="target",
        url="http://x/t",
        year=2018,
        make="NoSuchMake",
        model="NoSuchModel",
        mileage=50000,
        price=15000,
        classification="private_seller",
    )
    db_session.add(target)
    db_session.flush()
    est = estimate(db_session, target)
    assert est.sample_size == 0
    assert est.verdict == "unknown"


def test_market_endpoint(client, db_session):
    _seed_comps(db_session, count=5)
    target = Listing(
        source="craigslist",
        external_id="target",
        url="http://x/t",
        year=2018,
        make="Ford",
        model="F-150",
        mileage=85000,
        price=20000,
        classification="private_seller",
    )
    db_session.add(target)
    db_session.flush()

    r = client.get(f"/listings/{target.id}/market")
    assert r.status_code == 200
    body = r.json()
    assert body["sample_size"] == 5
    assert body["verdict"] in {"below", "at", "above"}
