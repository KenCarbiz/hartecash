"""CSV import for dealer migration (VAN / Frazer / DealerSocket / generic).

POST /leads/import.csv accepts multipart-form OR raw CSV bytes. Headers
match a permissive alias list (case-insensitive) so spreadsheets from
different vendors all work without preprocessing.
"""

from sqlalchemy import select

from fsbo.models import Lead, Listing


def _csv_post(client, csv_text: str):
    return client.post(
        "/leads/import.csv",
        content=csv_text.encode("utf-8"),
        headers={"Content-Type": "text/csv"},
    )


def test_basic_import_creates_listings_and_leads(client, db_session):
    csv_text = (
        "phone,year,make,model,price,city,state\n"
        "(813) 555-0101,2018,Honda,Accord,18500,Tampa,FL\n"
        "(813) 555-0102,2020,Toyota,Tacoma,32000,Tampa,FL\n"
    )
    r = _csv_post(client, csv_text)
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 2
    assert body["skipped_duplicates"] == 0
    assert body["errors"] == []

    listings = db_session.scalars(
        select(Listing).where(Listing.source == "csv_import")
    ).all()
    assert len(listings) == 2
    leads = db_session.scalars(
        select(Lead).where(Lead.dealer_id == "demo-dealer")
    ).all()
    assert len(leads) == 2
    # Listing fields populated correctly
    by_phone = {lst.seller_phone: lst for lst in listings}
    accord = by_phone["(813) 555-0101"]
    assert accord.year == 2018
    assert accord.make == "Honda"
    assert accord.model == "Accord"
    assert accord.price == 18500
    assert accord.state == "FL"


def test_header_aliases_are_case_insensitive(client, db_session):
    """VAN export uses 'Phone' / 'Vehicle Year'; Frazer uses 'cell'."""
    csv_text = (
        "Cell,Vehicle Year,Vehicle Make,Vehicle Model,Asking Price\n"
        "813-555-0103,2019,Ford,F-150,28000\n"
    )
    r = _csv_post(client, csv_text)
    assert r.status_code == 200
    assert r.json()["imported"] == 1
    listing = db_session.scalar(
        select(Listing).where(Listing.source == "csv_import")
    )
    assert listing is not None
    assert listing.year == 2019
    assert listing.make == "Ford"
    assert listing.price == 28000


def test_re_import_dedupes_existing_leads(client, db_session):
    csv_text = (
        "phone,year,make,model\n"
        "(813) 555-0104,2018,Honda,Accord\n"
    )
    first = _csv_post(client, csv_text).json()
    assert first["imported"] == 1

    # Import the exact same row again — should skip as duplicate.
    second = _csv_post(client, csv_text).json()
    assert second["imported"] == 0
    assert second["skipped_duplicates"] == 1

    # Only one listing + one lead in the DB.
    leads = db_session.scalars(
        select(Lead).where(Lead.dealer_id == "demo-dealer")
    ).all()
    assert len(leads) == 1


def test_row_without_identifier_errors(client, db_session):
    csv_text = (
        "year,make,model\n"
        "2018,Honda,Accord\n"
        "2020,Toyota,Tacoma\n"
    )
    # Header has no phone/email/vin, but the columns recognized include
    # year/make/model; rows still need an identifier on top of vehicle.
    r = _csv_post(client, csv_text)
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 0
    assert len(body["errors"]) == 2


def test_unrecognized_headers_are_silently_dropped(client, db_session):
    csv_text = (
        "phone,year,make,internal_dms_id,extra_color_pref\n"
        "(813) 555-0105,2018,Honda,XYZ-99,blue\n"
    )
    r = _csv_post(client, csv_text)
    assert r.status_code == 200
    assert r.json()["imported"] == 1


def test_no_recognized_headers_400s(client, db_session):
    csv_text = (
        "internal_dms_id,extra_color_pref\n"
        "XYZ,blue\n"
    )
    r = _csv_post(client, csv_text)
    assert r.status_code == 400
    assert "no recognized columns" in r.json()["detail"]


def test_status_field_normalized(client, db_session):
    csv_text = (
        "phone,year,make,model,status\n"
        "(813) 555-0106,2018,Honda,Accord,Negotiating\n"
        "(813) 555-0107,2018,Honda,Civic,bogus_status\n"
    )
    r = _csv_post(client, csv_text)
    assert r.status_code == 200
    leads = db_session.scalars(
        select(Lead).where(Lead.dealer_id == "demo-dealer")
    ).all()
    statuses = sorted(lead.status for lead in leads)
    # bogus falls back to 'new', valid one is preserved.
    assert statuses == ["negotiating", "new"]


def test_assigned_to_imported(client, db_session):
    csv_text = (
        "phone,year,make,model,owner\n"
        "(813) 555-0108,2018,Honda,Accord,rep@dealer.com\n"
    )
    r = _csv_post(client, csv_text)
    assert r.status_code == 200
    lead = db_session.scalar(select(Lead).where(Lead.dealer_id == "demo-dealer"))
    assert lead.assigned_to == "rep@dealer.com"


def test_price_with_dollar_sign_and_commas(client, db_session):
    csv_text = (
        "phone,year,make,model,asking price,miles\n"
        '(813) 555-0109,2018,Honda,Accord,"$18,500","120,000 mi"\n'
    )
    r = _csv_post(client, csv_text)
    assert r.status_code == 200
    listing = db_session.scalar(
        select(Listing).where(Listing.source == "csv_import")
    )
    assert listing.price == 18500
    assert listing.mileage == 120000


def test_empty_body_400s(client, db_session):
    r = client.post(
        "/leads/import.csv",
        content=b"",
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 400


def test_multipart_upload_works(client, db_session):
    csv_text = (
        "phone,year,make,model\n"
        "(813) 555-0110,2018,Honda,Accord\n"
    )
    r = client.post(
        "/leads/import.csv",
        files={"file": ("leads.csv", csv_text, "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["imported"] == 1


def test_import_is_dealer_scoped(client, db_session):
    """Other dealer's prior import doesn't collide with mine."""
    csv_text = (
        "phone,year,make,model\n"
        "(813) 555-0111,2018,Honda,Accord\n"
    )
    # Other dealer imports
    other = client.post(
        "/leads/import.csv",
        content=csv_text.encode("utf-8"),
        headers={"Content-Type": "text/csv", "X-Dealer-Id": "other-dealer"},
    )
    assert other.status_code == 200

    # Mine imports the same — listing is reused (same external_id) but
    # I get my own lead.
    mine = _csv_post(client, csv_text).json()
    assert mine["imported"] == 1

    leads = db_session.scalars(select(Lead)).all()
    dealers = {lead.dealer_id for lead in leads}
    assert dealers == {"demo-dealer", "other-dealer"}


def test_row_cap_enforced(client, db_session):
    """5000 rows is the cap; anything beyond is reported as an error."""
    rows = ["phone,year,make,model"]
    for i in range(5005):
        rows.append(f"(813) 555-{i:04d},2018,Honda,Accord")
    csv_text = "\n".join(rows) + "\n"
    r = _csv_post(client, csv_text)
    assert r.status_code == 200
    body = r.json()
    # 5000 imported, the rest dropped with an error pointing at the cap.
    assert body["imported"] == 5000
    assert any("row cap" in err["error"] for err in body["errors"])
