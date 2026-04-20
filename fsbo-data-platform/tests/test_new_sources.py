import httpx
import pytest
import respx

from fsbo.sources.bring_a_trailer import BringATrailerSource
from fsbo.sources.ksl import KSLClassifiedsSource
from fsbo.sources.privateauto import PrivateAutoSource


_KSL_PAGE = """
<html><head><script type="application/ld+json">
{
  "@type": "Vehicle",
  "name": "2019 Toyota 4Runner TRD",
  "url": "https://cars.ksl.com/listing/6789",
  "description": "One owner, all service records",
  "vehicleModelDate": "2019",
  "manufacturer": {"@type": "Brand", "name": "Toyota"},
  "model": "4Runner",
  "mileageFromOdometer": {"@type": "QuantitativeValue", "value": 58000, "unitCode": "SMI"},
  "vehicleIdentificationNumber": "JTEZU5JR8K5222111",
  "offers": {"@type": "Offer", "price": "32500", "priceCurrency": "USD"},
  "image": ["https://img.ksl.com/a.jpg", "https://img.ksl.com/b.jpg"]
}
</script></head><body>ksl</body></html>
"""


_PRIVATEAUTO_PAGE = """
<html><head></head><body>
<script id="__NEXT_DATA__" type="application/json">
{
  "props": {
    "pageProps": {
      "listings": [
        {
          "id": "abc123",
          "slug": "2020-honda-civic-sport",
          "title": "2020 Honda Civic Sport",
          "description": "Clean title, garage kept",
          "year": 2020,
          "make": "Honda",
          "model": "Civic",
          "trim": "Sport",
          "mileage": 42000,
          "price": 18500,
          "vin": "2HGFC2F55LH500001",
          "location": {"city": "Phoenix", "state": "AZ", "zip": "85001"},
          "images": [{"url": "https://cdn.privateauto.com/1.jpg"}]
        },
        {
          "id": "def456",
          "slug": "2018-jeep-wrangler",
          "title": "2018 Jeep Wrangler",
          "year": 2018,
          "make": "Jeep",
          "model": "Wrangler",
          "price": 27500,
          "location": {"city": "Dallas", "state": "TX"}
        }
      ]
    }
  }
}
</script>
</body></html>
"""


_BAT_LISTING_PAGE = """
<html><head><script type="application/ld+json">
{
  "@type": "Product",
  "name": "1995 Porsche 911 Carrera",
  "description": "Silver over black, 45k miles, well documented",
  "manufacturer": {"@type": "Brand", "name": "Porsche"},
  "model": "911",
  "offers": {"@type": "Offer", "highPrice": "68500", "priceCurrency": "USD"},
  "image": ["https://bringatrailer.com/img.jpg"]
}
</script></head><body>bat</body></html>
"""

_BAT_AUCTIONS_INDEX = """
<html><body>
<a href="/listing/1995-porsche-911-carrera-4/">1995 Porsche 911</a>
<a href="/listing/1997-acura-integra-type-r/">1997 Acura</a>
</body></html>
"""


@pytest.mark.asyncio
async def test_ksl_parses_jsonld_vehicle():
    with respx.mock() as mock:
        mock.get(url__startswith="https://cars.ksl.com/search").mock(
            return_value=httpx.Response(200, text=_KSL_PAGE)
        )
        source = KSLClassifiedsSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch(make="Toyota")]
        await source.aclose()
    assert len(results) == 1
    r = results[0]
    assert r.year == 2019
    assert r.make == "Toyota"
    assert r.model == "4Runner"
    assert r.mileage == 58000
    assert r.price == 32500.0
    assert r.vin == "JTEZU5JR8K5222111"


@pytest.mark.asyncio
async def test_privateauto_parses_next_data():
    with respx.mock() as mock:
        mock.get(url__startswith="https://privateauto.com/cars-for-sale").mock(
            return_value=httpx.Response(200, text=_PRIVATEAUTO_PAGE)
        )
        source = PrivateAutoSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch(zip_code="85001")]
        await source.aclose()
    assert len(results) == 2
    civic = results[0]
    assert civic.external_id == "abc123"
    assert civic.year == 2020
    assert civic.make == "Honda"
    assert civic.model == "Civic"
    assert civic.trim == "Sport"
    assert civic.price == 18500.0
    assert civic.city == "Phoenix"
    assert civic.state == "AZ"
    assert len(civic.images) == 1


@pytest.mark.asyncio
async def test_bat_walks_index_and_parses_detail():
    with respx.mock() as mock:
        mock.get(url="https://bringatrailer.com/auctions/").mock(
            return_value=httpx.Response(200, text=_BAT_AUCTIONS_INDEX)
        )
        mock.get(url__startswith="https://bringatrailer.com/listing/").mock(
            return_value=httpx.Response(200, text=_BAT_LISTING_PAGE)
        )
        source = BringATrailerSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch(limit=2)]
        await source.aclose()
    assert len(results) == 2
    assert all(r.make == "Porsche" for r in results)


@pytest.mark.asyncio
async def test_ksl_handles_fetch_failure():
    with respx.mock() as mock:
        mock.get(url__startswith="https://cars.ksl.com/search").mock(
            return_value=httpx.Response(503)
        )
        source = KSLClassifiedsSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch()]
        await source.aclose()
    assert results == []
