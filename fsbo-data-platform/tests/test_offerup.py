import httpx
import pytest
import respx

from fsbo.sources.offerup import OfferUpSource


_JSONLD_PAGE = """
<html>
  <head>
    <script type="application/ld+json">
    [
      {
        "@type": "Product",
        "name": "2019 Ford F-150 XLT",
        "description": "Clean title, one owner",
        "url": "https://offerup.com/item/detail/abc123",
        "image": "https://cdn.offerup.com/img/abc.jpg",
        "offers": {"@type": "Offer", "price": "22500", "priceCurrency": "USD"}
      },
      {
        "@type": "Product",
        "name": "2017 Toyota Tacoma",
        "url": "https://offerup.com/item/detail/def456",
        "offers": {"@type": "Offer", "price": "19800"}
      }
    ]
    </script>
  </head>
  <body>marketplace</body>
</html>
"""


@pytest.mark.asyncio
async def test_offerup_requires_proxy(monkeypatch):
    # No PROXY_URL set — source refuses to run.
    monkeypatch.setattr("fsbo.sources.offerup.settings.proxy_url", "", raising=True)
    source = OfferUpSource()
    results = [x async for x in source.fetch(q="ford")]
    assert results == []
    await source.aclose()


@pytest.mark.asyncio
async def test_offerup_parses_jsonld(monkeypatch):
    monkeypatch.setattr(
        "fsbo.sources.offerup.settings.proxy_url", "http://proxy:8080", raising=True
    )
    with respx.mock() as mock:
        mock.get(url__startswith="https://offerup.com/search").mock(
            return_value=httpx.Response(200, text=_JSONLD_PAGE)
        )
        source = OfferUpSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch(q="truck")]
        await source.aclose()

    assert len(results) == 2
    assert results[0].title == "2019 Ford F-150 XLT"
    assert results[0].year == 2019
    assert results[0].price == 22500.0
    assert results[0].external_id == "abc123"
    assert results[1].year == 2017


@pytest.mark.asyncio
async def test_offerup_blocks_get_skipped(monkeypatch):
    monkeypatch.setattr(
        "fsbo.sources.offerup.settings.proxy_url", "http://proxy:8080", raising=True
    )
    with respx.mock() as mock:
        mock.get(url__startswith="https://offerup.com/search").mock(
            return_value=httpx.Response(403, text="blocked")
        )
        source = OfferUpSource(client=httpx.AsyncClient())
        results = [x async for x in source.fetch(q="truck")]
        await source.aclose()
    assert results == []  # graceful no-op, doesn't raise
