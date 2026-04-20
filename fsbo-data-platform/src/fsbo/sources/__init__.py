from fsbo.sources.base import NormalizedListing, Source
from fsbo.sources.bring_a_trailer import BringATrailerSource
from fsbo.sources.craigslist import CraigslistSource
from fsbo.sources.ebay import EbayMotorsSource
from fsbo.sources.ksl import KSLClassifiedsSource
from fsbo.sources.offerup import OfferUpSource
from fsbo.sources.privateauto import PrivateAutoSource

REGISTRY: dict[str, type[Source]] = {
    "craigslist": CraigslistSource,
    "ebay_motors": EbayMotorsSource,
    "offerup": OfferUpSource,
    "ksl": KSLClassifiedsSource,
    "privateauto": PrivateAutoSource,
    "bring_a_trailer": BringATrailerSource,
}


__all__ = ["NormalizedListing", "Source", "REGISTRY"]
