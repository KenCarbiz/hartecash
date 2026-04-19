from fsbo.sources.base import NormalizedListing, Source
from fsbo.sources.craigslist import CraigslistSource
from fsbo.sources.ebay import EbayMotorsSource

REGISTRY: dict[str, type[Source]] = {
    "craigslist": CraigslistSource,
    "ebay_motors": EbayMotorsSource,
}


__all__ = ["NormalizedListing", "Source", "REGISTRY"]
