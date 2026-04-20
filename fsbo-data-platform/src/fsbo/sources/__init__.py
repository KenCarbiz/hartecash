from fsbo.sources.base import NormalizedListing, Source
from fsbo.sources.craigslist import CraigslistSource
from fsbo.sources.ebay import EbayMotorsSource
from fsbo.sources.offerup import OfferUpSource

REGISTRY: dict[str, type[Source]] = {
    "craigslist": CraigslistSource,
    "ebay_motors": EbayMotorsSource,
    "offerup": OfferUpSource,
}


__all__ = ["NormalizedListing", "Source", "REGISTRY"]
