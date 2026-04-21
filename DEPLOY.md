# AutoCurb — Deploy

Two services + Postgres. Also an optional scheduler worker. Each is
independently deployable; the reference `docker-compose.prod.yml` ties
them together for single-host deploys.

## Prerequisites

- Docker 24+ or any OCI-compatible runtime
- Postgres 15+ (use the `postgres:16-alpine` image if you don't have one)
- A domain + TLS (cookies are `Secure` in production)

## Single-host reference (Fly.io / Render / Railway / a $5 VPS)

1. Copy env template and fill in secrets:

   ```bash
   cp .env.prod.example .env.prod
   # edit POSTGRES_PASSWORD, JWT_SECRET (>=32 chars), API keys, etc.
   ```

2. Build and start:

   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
   ```

3. On first boot, the `api` service runs `alembic upgrade head`
   automatically, then serves on `:8000`. `web` serves on `:3000`. Put a
   reverse proxy (Caddy / nginx / Cloudflare) in front and terminate TLS.

## Split deploys (recommended at scale)

Each service has its own `Dockerfile`. Deploy them to separate platforms
if you want managed Postgres + autoscaling:

- **API** (`fsbo-data-platform/Dockerfile`): Fly.io machines, Render web
  service, Railway, AWS App Runner. Point `DATABASE_URL` at a managed
  Postgres (Neon / Supabase / RDS).
- **Scheduler** (same image, CMD `python -m fsbo.workers.scheduler`):
  run as a single worker instance. Do NOT run multiple schedulers —
  they'll double-poll. Use Fly cron / Render cron jobs / K8s CronJob.
- **Web** (`web/Dockerfile`): Vercel also works directly (no Docker
  needed). Set `FSBO_API_URL` to the public API origin.

## Required environment

**API service**

```
DATABASE_URL=postgresql+psycopg://user:pass@host/db
ENV_MODE=production                    # rejects X-Dealer-Id header spoofing
JWT_SECRET=<openssl rand -hex 32>      # >=32 bytes
COOKIE_SECURE=true
COOKIE_DOMAIN=.autocurb.example        # optional, for cross-subdomain SSO
SESSION_DAYS=14

# Optional integrations — each unlocks one enrichment or source
ANTHROPIC_API_KEY=                     # AI opener + classifier fallback
EBAY_APP_ID / EBAY_CERT_ID / EBAY_DEV_ID
MARKETCHECK_API_KEY=                   # Autotrader/Cars.com/CarGurus legal feed
PROXY_URL=http://user:pass@proxy:8080  # residential proxy for OfferUp etc.
TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN
TWILIO_MESSAGING_SERVICE_SID           # A2P 10DLC registered service
TWILIO_STATUS_CALLBACK=https://api.autocurb.example/webhooks/twilio/status
```

**Web service**

```
FSBO_API_URL=https://api.autocurb.example
NODE_ENV=production
```

## Migrations

Run `alembic upgrade head` from inside the API container whenever new
migrations ship. The compose file does this automatically on boot; for
multi-replica deploys prefer a one-shot job / release command.

## Seeding demo data (optional)

```bash
docker compose -f docker-compose.prod.yml exec api python scripts/seed_demo.py --count 100
```

## First user

No sign-up page gate is implemented — anyone reaching `/register` can
create a dealer. If you want single-tenant deploys, reverse-proxy block
`/register` after the first user is created, or set `DISABLE_REGISTER=1`
and add a startup check (TODO).

## Health checks

- `GET /health` → `{"status": "ok"}` on the API
- Web serves `/` (redirects to `/login` unauthenticated, HTTP 200 with
  session cookie)

## Chrome extension

The `extension/` directory builds to `extension/dist/`:

```bash
cd extension && npm install && npm run build
```

Load unpacked at `chrome://extensions/`. The popup lets each dealer
set their API URL, dealer ID (or paste an `ac_live_...` API key), and
user label. Distribute through the Chrome Web Store after your
listing passes review.

## Scaling notes

- The API is stateless; horizontally scale behind a load balancer.
- The scheduler must be a single instance (token buckets are in-process).
  Migrate to Redis-backed rate-limiting when running multi-replica.
- Webhook delivery worker currently runs inside the scheduler. Pull it
  into its own service if throughput demands.
- Postgres indexes are tuned for our current query patterns. Add a
  GIN index on `listings.description` once you exceed ~5M rows and
  full-text search latency hurts.

## Security checklist

- [ ] `ENV_MODE=production` set on the API
- [ ] `JWT_SECRET` rotated from the default 32+ byte value
- [ ] `COOKIE_SECURE=true`
- [ ] TLS everywhere (ACME/Let's Encrypt)
- [ ] Postgres not exposed to the public internet
- [ ] API keys stored hashed (already done)
- [ ] A2P 10DLC brand/campaign registered before SMS traffic
- [ ] Terms of Service + Privacy Policy published
- [ ] Legal review of any scraping sources before enabling (see per-source notes)
