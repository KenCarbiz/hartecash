# AutoCurb on Fly.io — step-by-step

End-to-end deploy in about 20 minutes. You ship three apps on Fly:
**autocurb-db** (Postgres), **autocurb-api** (FastAPI), **autocurb-web**
(Next.js dashboard), plus **autocurb-scheduler** for background jobs.

Prerequisites:
- `fly` CLI installed + logged in (`fly auth login`)
- A domain (optional; Fly gives you `*.fly.dev` subdomains for free)
- A SendGrid API key (for email alerts + password reset)

## 1. Postgres

```bash
fly postgres create \
  --name autocurb-db \
  --region iad \
  --initial-cluster-size 1 \
  --vm-size shared-cpu-1x \
  --volume-size 10
```

Fly prints a connection string — you won't need it directly, we'll
`attach` instead.

## 2. API service

```bash
cd fsbo-data-platform

fly launch \
  --no-deploy \
  --copy-config \
  --dockerfile Dockerfile \
  --name autocurb-api \
  --region iad

# Attach Postgres — sets DATABASE_URL automatically on the app.
fly postgres attach --app autocurb-api autocurb-db

# Secrets that ship with the API.
fly secrets set --app autocurb-api \
  JWT_SECRET=$(openssl rand -hex 32) \
  COOKIE_DOMAIN=.autocurb.example \
  APP_ORIGIN=https://app.autocurb.example \
  ANTHROPIC_API_KEY=sk-ant-... \
  SENDGRID_API_KEY=SG... \
  EMAIL_FROM=noreply@autocurb.example \
  EBAY_APP_ID=... \
  EBAY_CERT_ID=...

fly deploy
```

The `release_command` runs `alembic upgrade head` before the new
machine accepts traffic. Check:

```bash
fly logs --app autocurb-api | head -50
curl https://autocurb-api.fly.dev/health
```

Expect `{"status": "ok"}`. Create your first account:

```bash
curl -X POST https://autocurb-api.fly.dev/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@yourdealer.com","password":"supersecret123","dealer_name":"Your Dealer"}'
```

## 3. Scheduler service

The scheduler **must** be a single instance (in-process rate limiters
and a leader-only webhook drain loop). Deploy as a separate app so
you can scale the API horizontally without double-scheduling.

```bash
cd fsbo-data-platform

fly launch \
  --no-deploy \
  --copy-config \
  --config fly.scheduler.toml \
  --dockerfile Dockerfile \
  --name autocurb-scheduler \
  --region iad

fly postgres attach --app autocurb-scheduler autocurb-db

fly secrets set --app autocurb-scheduler \
  APP_ORIGIN=https://app.autocurb.example \
  ANTHROPIC_API_KEY=sk-ant-... \
  SENDGRID_API_KEY=SG... \
  EMAIL_FROM=noreply@autocurb.example \
  EBAY_APP_ID=... \
  EBAY_CERT_ID=...

fly deploy --config fly.scheduler.toml

# Make sure it stays at 1 machine forever.
fly scale count 1 --app autocurb-scheduler
```

Tail logs to confirm the jobs are firing:

```bash
fly logs --app autocurb-scheduler
# Expect: scheduler.started jobs=['craigslist','webhooks','vin_vision','image_hash','lead_alerts']
```

## 4. Web (dashboard)

```bash
cd web

fly launch \
  --no-deploy \
  --copy-config \
  --dockerfile Dockerfile \
  --name autocurb-web \
  --region iad

fly secrets set --app autocurb-web \
  FSBO_API_URL=https://autocurb-api.fly.dev

fly deploy
```

Visit `https://autocurb-web.fly.dev` — you should get the login page.

## 5. Custom domains (optional)

```bash
# Point your DNS A records at Fly:
fly ips list --app autocurb-api
fly ips list --app autocurb-web

# Then tell Fly about the custom hostnames:
fly certs add api.autocurb.example --app autocurb-api
fly certs add app.autocurb.example --app autocurb-web
```

Update the API's `COOKIE_DOMAIN` and both services' URL secrets so
`/auth/me` + session cookies work across subdomains.

## 6. Post-deploy smoke test

1. Hit `https://app.autocurb.example` → sign in
2. Save a search that matches a common vehicle in your area
3. Enable alerts on the search (🔔 toggle)
4. Ingest a demo hot lead:

   ```bash
   fly ssh console --app autocurb-api
   python scripts/seed_demo.py --count 5
   ```

5. Within 2 minutes you should receive the hot-lead email with a link
   back to `/listings/{id}`.
6. Reset the password flow: go to `/forgot-password`, enter your
   email, check inbox.

## Costs (ballpark)

- Postgres dev-tier: **~$2/mo**
- API shared-1x 512MB: **~$2/mo**
- Scheduler shared-1x 512MB: **~$2/mo**
- Web shared-1x 512MB: **~$2/mo**
- SendGrid free tier: **$0** (100 emails/day)
- Bandwidth: first 160 GB free

Plus whatever usage-based bills you rack up on Anthropic + Twilio +
Marketcheck. A single-dealer pilot lands under **$15/mo** in
infrastructure before the AI + SMS spend.

## Scaling later

- Scale API horizontally: `fly scale count 2 --app autocurb-api`
- Move the rate limiter to Redis before scaling the scheduler beyond 1
- Put Cloudflare in front for caching + WAF
- Pin a dedicated Fly region per metro when latency matters
