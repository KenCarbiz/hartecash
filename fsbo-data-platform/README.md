# fsbo-data-platform

Private-party (FSBO) vehicle listing aggregation platform. Collects, cleans, dedups,
and serves listings from public marketplaces via a REST API.

Designed to be consumed by dealer-facing products (e.g. AutoCurb) as a separate
service. Will be extracted into its own repo once API contracts stabilize
(~month 3-4).

## Architecture

```
 sources/      --> fetch raw listings from each marketplace
 workers/      --> scheduled pollers + job queue
 enrichment/   --> dedup, VIN OCR, LLM classification (dealer/scam/private)
 api/          --> FastAPI service exposing /listings
 storage/      --> Postgres (listings, sellers, sources), S3 (images)
```

## Current sources

| Source      | Method               | Status      | Legal posture                        |
|-------------|----------------------|-------------|--------------------------------------|
| Craigslist  | RSS feeds            | implemented | public data, RSS intended for this   |
| eBay Motors | Browse API (OAuth)   | stub        | official API                         |
| Autotrader  | HTML scrape + proxy  | planned     | ToS review needed                    |
| Cars.com    | HTML scrape + proxy  | planned     | ToS review needed                    |
| Facebook MP | Browser extension    | planned     | user-initiated via extension         |

## Local dev

```bash
cp .env.example .env
docker compose up -d postgres
pip install -e ".[dev]"
alembic upgrade head
uvicorn fsbo.api.main:app --reload
python -m fsbo.workers.poll --source craigslist --city tampa
```

## API

```
GET /listings?zip=33607&make=ford&year_min=2018&classification=private_seller
GET /listings/{id}
GET /sources
GET /health
```
