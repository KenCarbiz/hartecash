"""Regression tests for the craigslist breakage-detection paths.

The original behavior swallowed per-entry exceptions silently. If
Craigslist changed their RSS shape and every entry failed to parse,
fetch() returned successfully with 0 entries — operator never knew.
"""

import httpx
import pytest

from fsbo.sources.craigslist import CraigslistSource

RSS_GOOD = """<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>tampa cars - by owner</title>
    <link>https://tampa.craigslist.org/search/cta?format=rss</link>
    <description>tampa cars - by owner</description>
    <item>
      <title>2019 Honda Accord Sport - $18,500</title>
      <link>https://tampa.craigslist.org/hil/cto/d/tampa/7712345678.html</link>
      <description>One owner clean title</description>
      <dc:date>2026-05-05T12:00:00Z</dc:date>
    </item>
  </channel>
</rss>
"""

# Bozo: not RSS at all. Craigslist's hostile-bot page returns this kind
# of HTML when their bot detector fires.
RSS_BOZO = "<html><body>Sorry, you're a robot</body></html>"


def _client(body: str, status: int = 200) -> httpx.AsyncClient:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(status, text=body, headers={"Content-Type": "application/rss+xml"})
    )
    return httpx.AsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_fetch_yields_entry_on_good_rss():
    src = CraigslistSource(client=_client(RSS_GOOD))
    try:
        items = []
        async for n in src.fetch(city="tampa"):
            items.append(n)
        assert len(items) == 1
        assert items[0].source == "craigslist"
        assert items[0].external_id == "7712345678"
    finally:
        await src.aclose()


@pytest.mark.asyncio
async def test_fetch_raises_when_rss_is_unparseable():
    """Bot-detector HTML page must surface as a failed run, not silent 0."""
    src = CraigslistSource(client=_client(RSS_BOZO))
    try:
        with pytest.raises(RuntimeError, match="unparseable"):
            async for _ in src.fetch(city="tampa"):
                pass
    finally:
        await src.aclose()


# RSS with entries that all fail to parse (e.g. <item> shape changed
# so _extract_id can't find anything). We trigger this by deleting
# the link tag inside an item.
RSS_ALL_PARSE_FAIL = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>x</title>
    <link>x</link>
    <description>x</description>
    <item><foo>bar</foo></item>
    <item><foo>bar</foo></item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_fetch_raises_when_every_entry_fails_to_parse(monkeypatch):
    """Force parse_entry to raise for every item -> 0 yields, expect raise."""
    src = CraigslistSource(client=_client(RSS_ALL_PARSE_FAIL))

    def boom(self, entry, city):
        raise ValueError("parse broken")

    monkeypatch.setattr(CraigslistSource, "_parse_entry", boom)
    try:
        with pytest.raises(RuntimeError, match="schema appears broken"):
            async for _ in src.fetch(city="tampa"):
                pass
    finally:
        await src.aclose()
