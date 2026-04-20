from fsbo.models import Listing
from fsbo.webhooks.delivery import matches_filters, sign_payload


def test_sign_payload_is_deterministic():
    body = b'{"event":"listing.created"}'
    assert sign_payload("secret", body) == sign_payload("secret", body)


def test_sign_payload_differs_by_secret():
    body = b'{"event":"listing.created"}'
    assert sign_payload("secret-a", body) != sign_payload("secret-b", body)


def test_filters_empty_always_matches():
    listing = Listing(source="craigslist", external_id="1", url="x", classification="private_seller")
    assert matches_filters(listing, {})


def test_filters_equality():
    listing = Listing(
        source="craigslist",
        external_id="1",
        url="x",
        make="Ford",
        state="FL",
        classification="private_seller",
    )
    assert matches_filters(listing, {"make": "Ford"})
    assert not matches_filters(listing, {"make": "Honda"})
    assert matches_filters(listing, {"state": "FL", "make": "Ford"})
    assert not matches_filters(listing, {"state": "FL", "make": "Honda"})


def test_filters_list_membership():
    listing = Listing(
        source="craigslist",
        external_id="1",
        url="x",
        state="FL",
        classification="private_seller",
    )
    assert matches_filters(listing, {"state": ["FL", "GA", "TX"]})
    assert not matches_filters(listing, {"state": ["CA", "OR"]})
