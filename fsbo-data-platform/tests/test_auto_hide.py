from fsbo.models import Listing


def _add(db, **kw):
    defaults = {
        "source": "craigslist",
        "url": "http://x",
        "title": "car",
        "classification": "private_seller",
    }
    defaults.update(kw)
    row = Listing(**defaults)
    db.add(row)
    db.flush()
    return row


def test_auto_hidden_excluded_by_default(client, db_session):
    _add(db_session, external_id="ok-1")
    _add(db_session, external_id="hidden-1", auto_hidden=True, auto_hide_reason="scam_score>=0.9")

    r = client.get("/listings?classification=")
    assert r.status_code == 200
    ids = [x["external_id"] for x in r.json()["items"]]
    assert "ok-1" in ids
    assert "hidden-1" not in ids


def test_show_hidden_includes_them(client, db_session):
    _add(db_session, external_id="ok-2")
    _add(db_session, external_id="hidden-2", auto_hidden=True)

    r = client.get("/listings?classification=&show_hidden=true")
    ids = [x["external_id"] for x in r.json()["items"]]
    assert "hidden-2" in ids
