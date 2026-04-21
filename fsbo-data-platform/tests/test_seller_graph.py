from fsbo.enrichment.seller_graph import (
    extract_emails,
    max_component_size,
    register_listing_identities,
)
from fsbo.models import Listing, SellerIdentity


def _listing(db, **kw):
    base = {
        "source": "facebook_marketplace",
        "external_id": "fb-1",
        "url": "http://x",
        "title": "2020 Civic",
        "classification": "private_seller",
    }
    base.update(kw)
    row = Listing(**base)
    db.add(row)
    db.flush()
    return row


def test_extract_emails():
    assert extract_emails("contact me at alice@example.com or bob@example.com") == [
        "alice@example.com",
        "bob@example.com",
    ]
    assert extract_emails(None) == []
    assert extract_emails("no email here") == []


def test_phone_identity_linked(db_session):
    listing = _listing(db_session, seller_phone="(813) 555-0101")
    idents = register_listing_identities(db_session, listing)
    assert len(idents) == 1
    assert idents[0].kind == "phone"
    assert idents[0].value == "8135550101"
    assert idents[0].listing_count == 1


def test_same_phone_across_listings_bumps_count(db_session):
    a = _listing(db_session, external_id="fb-a", seller_phone="(813) 555-0101")
    register_listing_identities(db_session, a)

    b = _listing(db_session, external_id="fb-b", seller_phone="+1-813-555-0101")
    register_listing_identities(db_session, b)

    c = _listing(db_session, external_id="fb-c", seller_phone="8135550101")
    register_listing_identities(db_session, c)

    # All three map to the same normalized phone identity
    ident = (
        db_session.query(SellerIdentity)
        .filter_by(kind="phone", value="8135550101")
        .first()
    )
    assert ident.listing_count == 3


def test_email_identity_from_description(db_session):
    listing = _listing(
        db_session,
        description="Text me at sketchy.seller@gmail.com — cash only.",
    )
    idents = register_listing_identities(db_session, listing)
    assert any(i.kind == "email" and "sketchy" in i.value for i in idents)


def test_image_phash_identity(db_session):
    listing = _listing(db_session, raw={"image_bg_phashes": ["abc1234567890def", "9876543210fedcba"]})
    idents = register_listing_identities(db_session, listing)
    kinds = [i.kind for i in idents]
    values = [i.value for i in idents]
    assert kinds.count("image_phash") == 2
    assert "abc1234567890def" in values


def test_max_component_size_catches_curbstoner(db_session):
    # Seed 5 listings sharing the same phone — the 5th listing's cluster
    # size (excluding itself) should be 4.
    for i in range(5):
        listing = _listing(
            db_session,
            external_id=f"fb-curb-{i}",
            seller_phone="(555) 100-0000",
        )
        register_listing_identities(db_session, listing)

    last = (
        db_session.query(Listing)
        .filter_by(external_id="fb-curb-4")
        .first()
    )
    assert max_component_size(db_session, last.id) == 4


def test_no_identities_returns_zero(db_session):
    listing = _listing(db_session, seller_phone=None)
    register_listing_identities(db_session, listing)
    assert max_component_size(db_session, listing.id) == 0


def test_shared_image_phash_clusters_across_profiles(db_session):
    # Same dealer lot, two different Facebook listings with different phones
    # but identical image-background phash. Graph catches the cluster.
    a = _listing(
        db_session,
        external_id="fb-bg-a",
        seller_phone="(555) 100-0001",
        raw={"image_bg_phashes": ["lot_hash_abcdef01"]},
    )
    register_listing_identities(db_session, a)
    b = _listing(
        db_session,
        external_id="fb-bg-b",
        seller_phone="(555) 100-0002",
        raw={"image_bg_phashes": ["lot_hash_abcdef01"]},
    )
    register_listing_identities(db_session, b)

    # Neither phone matches (unique), but the shared image-background
    # identity links them.
    assert max_component_size(db_session, b.id) == 1
