"""Plate-to-VIN cluster lookup against our own corpus.

When plate vision OCRs a plate that we've previously seen on a listing
with a VIN, that listing already did the plate->VIN translation for
us. We backfill the new listing's VIN from the historical match —
effectively a free plate-to-VIN decoder using zero external APIs.

Plate identity also feeds the seller-graph cluster size, which the
quality scorer reads for curbstoner detection.
"""

from fsbo.enrichment.seller_graph import (
    count_listings_sharing_plate,
    find_corpus_vin_for_plate,
    max_component_size,
    normalize_plate,
    register_listing_identities,
)
from fsbo.models import Listing


def test_normalize_plate_strips_separators():
    assert normalize_plate("7GTF 123") == "7GTF123"
    assert normalize_plate("7gtf-123") == "7GTF123"
    assert normalize_plate("ABC 1234") == "ABC1234"
    assert normalize_plate(None) == ""
    assert normalize_plate("  ") == ""


def test_register_creates_plate_identity(db_session):
    listing = Listing(
        source="craigslist",
        external_id="cl-plate-1",
        url="http://x",
        title="x",
        license_plate="7GTF123",
        license_plate_state="CA",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()

    register_listing_identities(db_session, listing)
    db_session.flush()

    # Same listing's plate cluster should size 1 (just itself); after
    # we exclude self from the cluster, the relevant signal is 0.
    assert max_component_size(db_session, listing.id) == 0


def test_plate_cluster_size_grows_across_listings(db_session):
    """Three listings under the same plate => max_component_size==2."""
    for i in range(3):
        listing = Listing(
            source="craigslist",
            external_id=f"cl-cluster-{i}",
            url=f"http://x/{i}",
            title=f"listing {i}",
            license_plate="7GTF123",
            classification="private_seller",
        )
        db_session.add(listing)
        db_session.flush()
        register_listing_identities(db_session, listing)
        db_session.flush()

    listings = db_session.query(Listing).filter(
        Listing.external_id.like("cl-cluster-%")
    ).all()
    # Excluding self, cluster has 2 other matching listings.
    for listing in listings:
        assert max_component_size(db_session, listing.id) == 2


def test_find_corpus_vin_returns_historical_match(db_session):
    # Old listing with both plate + VIN
    db_session.add(
        Listing(
            source="craigslist",
            external_id="old-vin-listing",
            url="http://x",
            title="2018 Honda Accord",
            license_plate="7GTF123",
            vin="1HGBH41JXMN109186",
            classification="private_seller",
        )
    )
    db_session.flush()

    # New listing with the same plate but no VIN yet
    new_listing = Listing(
        source="facebook_marketplace",
        external_id="new-no-vin",
        url="http://x",
        title="2018 Accord",
        license_plate="7GTF 123",  # different formatting
        classification="private_seller",
    )
    db_session.add(new_listing)
    db_session.flush()

    found = find_corpus_vin_for_plate(
        db_session, "7GTF 123", exclude_listing_id=new_listing.id
    )
    assert found == "1HGBH41JXMN109186"


def test_find_corpus_vin_returns_none_when_no_match(db_session):
    db_session.add(
        Listing(
            source="craigslist",
            external_id="other-plate",
            url="http://x",
            title="x",
            license_plate="ABC9999",
            vin="1HGBH41JXMN109186",
            classification="private_seller",
        )
    )
    db_session.flush()
    assert find_corpus_vin_for_plate(db_session, "7GTF123") is None


def test_count_listings_sharing_plate(db_session):
    for i in range(4):
        db_session.add(
            Listing(
                source="craigslist",
                external_id=f"share-{i}",
                url=f"http://x/{i}",
                title="x",
                license_plate="7GTF123",
                classification="private_seller",
            )
        )
    db_session.flush()
    listings = db_session.query(Listing).all()
    target = listings[0]
    assert (
        count_listings_sharing_plate(
            db_session, "7GTF123", exclude_listing_id=target.id
        )
        == 3
    )


def test_short_plate_does_not_cluster(db_session):
    # Plates < 4 chars are skipped (too generic / OCR-error-prone)
    listing = Listing(
        source="craigslist",
        external_id="short-plate",
        url="http://x",
        title="x",
        license_plate="ABC",
        classification="private_seller",
    )
    db_session.add(listing)
    db_session.flush()
    register_listing_identities(db_session, listing)
    assert find_corpus_vin_for_plate(db_session, "ABC") is None
    assert count_listings_sharing_plate(db_session, "ABC") == 0
