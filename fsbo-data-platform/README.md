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

# API server
uvicorn fsbo.api.main:app --reload

# One-shot poll
python -m fsbo.workers.poll --source craigslist --city tampa

# Continuous scheduler (polls 15+ cities + drains webhook queue)
python -m fsbo.workers.scheduler
```

## API

```
# Listings
GET    /listings?zip=33607&make=ford&year_min=2018&classification=private_seller
GET    /listings/{id}

# Webhooks (for AutoCurb / other consumers)
POST   /webhooks/subscriptions          # create, returns secret once
GET    /webhooks/subscriptions
DELETE /webhooks/subscriptions/{id}

GET    /sources
GET    /health
```

## Webhook delivery

Each `listing.created` event POSTs JSON to subscriber URLs with headers:

```
X-FSBO-Event:       listing.created
X-FSBO-Signature:   HMAC-SHA256 of raw body (hex) using subscription secret
X-FSBO-Delivery-Id: <delivery-id>
```

Retries with exponential backoff (30s, 2m, 10m, 1h, 6h) up to 5 attempts.
Subscription filters are AND-joined equality checks over listing fields, e.g.

```json
{"state": ["FL", "GA"], "make": "Ford"}
```

## Enrichment pipeline

1. Dedup key: VIN first, then phone+vehicle fingerprint.
2. VIN decode via NHTSA vPIC (free, no key) fills missing year/make/model/trim.
3. Classification: regex heuristics → Claude Haiku LLM for ambiguous cases.
4. Webhooks fire only on `private_seller` classifications.
