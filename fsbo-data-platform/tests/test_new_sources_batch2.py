import httpx
import pytest
import respx

from fsbo.sources.bookoo import BookooSource
from fsbo.sources.classic_cars import ClassicCarsSource
from fsbo.sources.el_clasificado import ElClasificadoSource
from fsbo.sources.hemmings import HemmingsSource
from fsbo.sources.marketcheck import MarketcheckSource
from fsbo.sources.recycler import RecyclerSource


_JSONLD_PAGE = """
<html><head>
<script type="application/ld+json">
{
  "@type": "Vehicle",
  "name": "1968 Chevrolet Camaro SS",
  "url": "https://example.com/listing/55512",
  "description": "Numbers matching, restored",
  "vehicleModelDate": "1968",
  "manufacturer": {"@type": "Brand", "name": "Chevrolet"},
  "model": "Camaro",
  "mileageFromOdometer": {"@type": "QuantitativeValue", "value": 76000},
  "vehicleIdentificationNumber": "124378N400123",
  "offers": {"@type": "Offer", "price": "62500", "priceCurrency": "USD"},
  "image": ["https://example.com/img1.jpg", "https://example.com/img2.jpg"]
}
</script>
</head><body>listing</body></html>
"""


_BOOKOO_PAGE = """
<html><body>
<div class="tile">
  <a href="/item/99812">2017 Ford F-150 XLT</a>
  <span>$22,500</span>
</div>
<div class="tile">
  <a href="/item/99813">2020 Honda CR-V</a>
  <span>$21,000</span>
</div>
</body></html>
"""


_MARKETCHECK_PAYLOAD = {
    "num_found": 2,
    "listings": [
        {
            "id": "ac-lst-1",
            "vin": "2HGFC2F55LH500001",
            "vdp_url": "https://www.autotrader.com/cars-for-sale/vehicledetails.xhtml?listingId=abc",
            "heading": "2019 Honda Accord",
            "price": 22500,
            "miles": 38000,
            "source": "autotrader",
            "build": {"year": 2019, "make": "Honda", "model": "Accord", "trim": "Sport"},
            "dealer": {"city": "Tampa", "state": "FL", "zip": "33607", "phone": "813-555-1111"},
            "media": {"photo_links": ["https://cdn.autotrader.com/1.jpg"]},
        },
        {
            "id": "ac-lst-2",
            "vin": "1G1ZC5E05FF1234567",
            "vdp_url": "https://www.cars.com/vehicledetail/def/",
            "heading": "2018 Chevrolet Malibu",
            "price": 15800,
            "miles": 52000,
            "source": "cars.com",
            "build": {"year": 2018, "make": "Chevrolet", "model": "Malibu"},
            "dealer": {"city": "Orlando", "state": "FL"},
            "media": {},
        },
    ],
}


@pytest.mark.asyncio
async def test_recycler_parses_jsonld():
    with respx.mock() as mock:
        mock.get(url__startswith="https://www.recycler.com/search").mock(
            return_value=httpx.Response(200, text=_JSONLD_PAGE)
        )
        source = RecyclerSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch(q="camaro")]
        await source.aclose()
    assert len(results) == 1
    assert results[0].year == 1968
    assert results[0].make == "Chevrolet"


@pytest.mark.asyncio
async def test_hemmings_parses_jsonld():
    with respx.mock() as mock:
        mock.get(url__startswith="https://www.hemmings.com").mock(
            return_value=httpx.Response(200, text=_JSONLD_PAGE)
        )
        source = HemmingsSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch(make="Chevrolet")]
        await source.aclose()
    assert len(results) == 1
    assert results[0].price == 62500.0


@pytest.mark.asyncio
async def test_classic_cars_parses_jsonld():
    with respx.mock() as mock:
        mock.get(url__startswith="https://classiccars.com/listings/find").mock(
            return_value=httpx.Response(200, text=_JSONLD_PAGE)
        )
        source = ClassicCarsSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch()]
        await source.aclose()
    assert len(results) == 1


@pytest.mark.asyncio
async def test_el_clasificado_parses_jsonld():
    with respx.mock() as mock:
        mock.get(url__startswith="https://www.elclasificado.com").mock(
            return_value=httpx.Response(200, text=_JSONLD_PAGE)
        )
        source = ElClasificadoSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch()]
        await source.aclose()
    assert len(results) == 1


@pytest.mark.asyncio
async def test_bookoo_parses_html_tiles():
    with respx.mock() as mock:
        mock.get(url__startswith="https://bookoo.com/search").mock(
            return_value=httpx.Response(200, text=_BOOKOO_PAGE)
        )
        source = BookooSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch()]
        await source.aclose()
    assert len(results) == 2
    titles = [r.title for r in results]
    assert "2017 Ford F-150 XLT" in titles
    assert all(r.price is not None for r in results)


@pytest.mark.asyncio
async def test_marketcheck_no_key_no_ops(monkeypatch):
    monkeypatch.setattr("fsbo.sources.marketcheck.settings.marketcheck_api_key", "", raising=True)
    source = MarketcheckSource(client=httpx.AsyncClient())
    results = [x async for x in source.fetch(make="Honda")]
    await source.aclose()
    assert results == []


@pytest.mark.asyncio
async def test_marketcheck_with_key_parses(monkeypatch):
    monkeypatch.setattr(
        "fsbo.sources.marketcheck.settings.marketcheck_api_key", "fake-key", raising=True
    )
    with respx.mock() as mock:
        mock.get(url__startswith="https://api.marketcheck.com/v2/search/car/active").mock(
            return_value=httpx.Response(200, json=_MARKETCHECK_PAYLOAD)
        )
        source = MarketcheckSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch(zip_code="33607")]
        await source.aclose()
    assert len(results) == 2
    # Source name should be prefixed with origin site
    assert results[0].source == "marketcheck:autotrader"
    assert results[1].source == "marketcheck:cars.com"
    assert results[0].year == 2019
    assert results[0].make == "Honda"


@pytest.mark.asyncio
async def test_graceful_503_on_jsonld_sources():
    with respx.mock() as mock:
        mock.get(url__startswith="https://www.recycler.com").mock(
            return_value=httpx.Response(503, text="busy")
        )
        source = RecyclerSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch()]
        await source.aclose()
    assert results == []


def test_registry_has_all_sources():
    from fsbo.sources import REGISTRY

    expected = {
        "craigslist",
        "ebay_motors",
        "offerup",
        "ksl",
        "privateauto",
        "bring_a_trailer",
        "recycler",
        "hemmings",
        "classic_cars",
        "bookoo",
        "el_clasificado",
        "marketcheck",
    }
    assert expected.issubset(set(REGISTRY.keys()))
    assert len(REGISTRY) >= 12
