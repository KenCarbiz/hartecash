from fsbo.sources.base import NormalizedListing, Source
from fsbo.sources.bookoo import BookooSource
from fsbo.sources.bring_a_trailer import BringATrailerSource
from fsbo.sources.classic_cars import ClassicCarsSource
from fsbo.sources.craigslist import CraigslistSource
from fsbo.sources.ebay import EbayMotorsSource
from fsbo.sources.el_clasificado import ElClasificadoSource
from fsbo.sources.hemmings import HemmingsSource
from fsbo.sources.ksl import KSLClassifiedsSource
from fsbo.sources.marketcheck import MarketcheckSource
from fsbo.sources.offerup import OfferUpSource
from fsbo.sources.privateauto import PrivateAutoSource
from fsbo.sources.recycler import RecyclerSource

REGISTRY: dict[str, type[Source]] = {
    "craigslist": CraigslistSource,
    "ebay_motors": EbayMotorsSource,
    "offerup": OfferUpSource,
    "ksl": KSLClassifiedsSource,
    "privateauto": PrivateAutoSource,
    "bring_a_trailer": BringATrailerSource,
    "recycler": RecyclerSource,
    "hemmings": HemmingsSource,
    "classic_cars": ClassicCarsSource,
    "bookoo": BookooSource,
    "el_clasificado": ElClasificadoSource,
    "marketcheck": MarketcheckSource,
}


__all__ = ["NormalizedListing", "Source", "REGISTRY"]
