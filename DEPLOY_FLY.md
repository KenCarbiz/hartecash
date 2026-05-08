# AutoAcquisition on Fly.io — step-by-step launch

End-to-end deploy in about 30 minutes. You ship four apps on Fly:
**aa-db** (Postgres), **aa-api** (FastAPI backend), **aa-web** (Next.js
dashboard), and **aa-scheduler** (background workers — must stay at 1
machine because of in-process locks).

## Prerequisites

- `fly` CLI installed: `curl -L https://fly.io/install.sh | sh`
- Logged in: `fly auth login`
- Payment method on your Fly account (the dev tiers are cheap — see Costs)
- These third-party accounts ready to paste keys from:
  - **Anthropic** — https://console.anthropic.com (Claude Haiku 4.5 for VIN OCR + voice intake)
  - **Twilio** — phone number + Auth Token (SMS + voice)
  - **SendGrid** — API key for transactional email; Inbound Parse for reply routing
  - **Stripe** — secret key + webhook signing secret + Price IDs for your plans
- A domain (optional; Fly gives you `*.fly.dev` for free if you skip step 6)

> **Note**: this doc replaces the older Lovable preview path. Fly is
> the production target.

---

## 1. Postgres

```bash
fly postgres create \
  --name aa-db \
  --region iad \
  --initial-cluster-size 1 \
  --vm-size shared-cpu-1x \
  --volume-size 10
```

Save the connection string Fly prints (you can also retrieve later via
`fly pg connect`). We'll `attach` it to each app instead of pasting.

---

## 2. API service (FastAPI backend)

```bash
cd fsbo-data-platform

fly launch \
  --no-deploy \
  --copy-config \
  --dockerfile Dockerfile \
  --name aa-api \
  --region iad

fly postgres attach --app aa-api aa-db
```

Set secrets. **Required for production safety** — the app refuses to
boot if `JWT_SECRET` is the default or `COOKIE_SECURE` is false:

```bash
fly secrets set --app aa-api \
  ENV_MODE=production \
  JWT_SECRET=$(openssl rand -hex 32) \
  COOKIE_SECURE=true \
  COOKIE_DOMAIN=.autoacquisition.io \
  APP_ORIGIN=https://app.autoacquisition.io \
  \
  ANTHROPIC_API_KEY=sk-ant-... \
  \
  TWILIO_ACCOUNT_SID=AC... \
  TWILIO_AUTH_TOKEN=... \
  TWILIO_FROM_NUMBER=+18135550123 \
  \
  SENDGRID_API_KEY=SG... \
  EMAIL_BACKEND=sendgrid \
  EMAIL_FROM=noreply@autoacquisition.io \
  EMAIL_FROM_NAME="AutoAcquisition" \
  INBOUND_EMAIL_TOKEN=$(openssl rand -hex 24) \
  \
  STRIPE_SECRET_KEY=sk_live_... \
  STRIPE_WEBHOOK_SECRET=whsec_... \
  STRIPE_PRICE_STARTER=price_... \
  STRIPE_PRICE_PRO=price_... \
  STRIPE_PRICE_PERFORMANCE=price_...
```

Optional (skip if you don't have these yet — features auto-degrade):

```bash
fly secrets set --app aa-api \
  EBAY_APP_ID=... \
  EBAY_CERT_ID=... \
  MARKETCHECK_API_KEY=... \
  CARFAX_API_KEY=... \
  AUTOCHECK_API_KEY=... \
  NMVTIS_API_KEY=...
```

Deploy. The `release_command` runs `alembic upgrade head` against the
attached Postgres before the new machine accepts traffic:

```bash
fly deploy
fly logs --app aa-api | head -50
curl https://aa-api.fly.dev/health
# {"status":"ok"}
```

Create the first admin account (your dealership):

```bash
curl -X POST https://aa-api.fly.dev/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@yourdealer.com","password":"a-strong-passphrase","dealer_name":"Your Dealer"}'
```

The first user becomes the dealer's admin (can invite teammates).

---

## 3. Scheduler service (background workers)

The scheduler **must stay at 1 machine** — it holds in-process locks
for the listing scraper, webhook drain, lead-alert worker, and the
TCPA quiet-hours cache. Run it as a separate app so the API can scale
horizontally without double-firing jobs.

```bash
cd fsbo-data-platform

fly launch \
  --no-deploy \
  --copy-config \
  --config fly.scheduler.toml \
  --dockerfile Dockerfile \
  --name aa-scheduler \
  --region iad

fly postgres attach --app aa-scheduler aa-db
```

Re-set the same secrets (the scheduler runs the same image):

```bash
fly secrets set --app aa-scheduler \
  ENV_MODE=production \
  APP_ORIGIN=https://app.autoacquisition.io \
  ANTHROPIC_API_KEY=sk-ant-... \
  TWILIO_ACCOUNT_SID=AC... \
  TWILIO_AUTH_TOKEN=... \
  TWILIO_FROM_NUMBER=+18135550123 \
  SENDGRID_API_KEY=SG... \
  EMAIL_BACKEND=sendgrid \
  EMAIL_FROM=noreply@autoacquisition.io
# (eBay / Marketcheck / Carfax keys too, if you set them on the API)

fly deploy --config fly.scheduler.toml
fly scale count 1 --app aa-scheduler   # CRITICAL: never let this go above 1
```

Confirm jobs are firing:

```bash
fly logs --app aa-scheduler
# Expect a line like:
#   scheduler.started jobs=['craigslist','webhooks','vin_vision',
#                           'image_hash','lead_alerts']
```

---

## 4. Web (Next.js dashboard)

```bash
cd web

fly launch \
  --no-deploy \
  --copy-config \
  --dockerfile Dockerfile \
  --name aa-web \
  --region iad

fly secrets set --app aa-web \
  FSBO_API_URL=https://aa-api.fly.dev

fly deploy
```

Visit `https://aa-web.fly.dev` — you should land on the login page
and be able to sign in with the admin account from step 2.

---

## 5. Wire up the third-party webhooks

After the apps are running, configure each external service to POST
back to your API:

### Twilio
- Phone Numbers → click your number → **Messaging → Webhook**:
  `https://aa-api.fly.dev/webhooks/twilio/inbound` (POST)
- **Voice → Status callback** (optional, for call analytics):
  `https://aa-api.fly.dev/voice/twiml/status/{call_id}`

### SendGrid Inbound Parse
- Settings → Inbound Parse → Add Host & URL
- URL: `https://aa-api.fly.dev/webhooks/email/inbound?token=<INBOUND_EMAIL_TOKEN>`
  (use the value you set in step 2)
- Spam check: ON; Send raw: OFF

Then point `MX leads.autoacquisition.io → mx.sendgrid.net` in DNS.

### Stripe
- Dashboard → Developers → Webhooks → Add endpoint
- URL: `https://aa-api.fly.dev/webhooks/stripe`
- Events: `checkout.session.completed`,
  `customer.subscription.{created,updated,deleted}`,
  `invoice.{paid,payment_failed}`
- Copy the signing secret → that's `STRIPE_WEBHOOK_SECRET` in step 2.
  **The API now refuses unsigned webhooks in production**, so this
  must be set or Stripe events 503.

---

## 6. Custom domains (recommended for launch)

```bash
# Get the IPs to point your DNS at:
fly ips list --app aa-api
fly ips list --app aa-web

# Add A records at your registrar:
#   api.autoacquisition.io  →  <aa-api ipv4>
#   app.autoacquisition.io  →  <aa-web ipv4>

# Tell Fly about the hostnames so it provisions Let's Encrypt:
fly certs add api.autoacquisition.io --app aa-api
fly certs add app.autoacquisition.io --app aa-web
```

After cert issuance (~1-5 min), update the secrets to use the custom
domains so cookies + redirects work across subdomains:

```bash
fly secrets set --app aa-api \
  APP_ORIGIN=https://app.autoacquisition.io \
  COOKIE_DOMAIN=.autoacquisition.io

fly secrets set --app aa-web \
  FSBO_API_URL=https://api.autoacquisition.io
```

Then redeploy both:

```bash
fly deploy --app aa-api
fly deploy --app aa-web
```

---

## 7. Post-deploy smoke test

1. **Login**: visit `https://app.autoacquisition.io`, sign in
2. **Onboarding checklist**: dashboard shows the 8-step setup panel.
   Each item links to the right settings surface.
3. **Save a search**: pick a city + vehicle type on `/welcome` so the
   scheduler has work to do
4. **Seed a demo lead** (one-shot, optional):
   ```bash
   fly ssh console --app aa-api
   python scripts/seed_demo.py --count 5
   ```
5. **Verify email alerts**: within 2 minutes of seeding, the rep
   email should land. Check inbox + Activity Log on `/analytics`.
6. **CSV import**: Settings → Import leads — upload a sample CSV
   (works with VAN / Frazer / DealerSocket exports unchanged).
7. **Click-to-call**: open any listing → "Call from your phone" →
   enter your cell. With Twilio creds set, your phone rings and
   bridges to the seller's number.
8. **Stripe checkout**: Settings → Billing → pick a plan. Use
   Stripe's test card `4242 4242 4242 4242` if you set up test keys.

---

## 8. Operational notes

**Background workers must stay at count=1.** If you ever do
`fly scale count 2 --app aa-scheduler`, the scrapers + webhook drain
will double-fire. To go beyond one scheduler, swap the in-process
rate limiter (`src/fsbo/auth/rate_limit.py`) for Redis first.

**The API can scale freely.**
```bash
fly scale count 3 --app aa-api
```
The 60s TCPA quiet-hours cache is per-process; the worst case is a
quiet-hours change taking up to 60s to propagate to all three boxes.

**Logs in one place:**
```bash
fly logs --app aa-api &
fly logs --app aa-scheduler &
fly logs --app aa-web &
wait
```

**Database migrations** ship automatically via `release_command` in
`fly.toml` (runs `alembic upgrade head` before the new machine takes
traffic). To inspect:
```bash
fly ssh console --app aa-api
alembic current
alembic history
```

---

## 9. Costs (small-scale launch ballpark)

- **aa-db** Postgres dev tier: **~$2/mo**
- **aa-api** shared-cpu-1x 512MB: **~$2/mo**
- **aa-scheduler** shared-cpu-1x 512MB: **~$2/mo**
- **aa-web** shared-cpu-1x 512MB: **~$2/mo**
- SendGrid free tier: **$0** (100 emails/day; bump to $20/mo at 50K)
- Bandwidth: first 160 GB free

**Fly infrastructure: ~$8/mo before traffic.**

Usage-based costs that are *not* on the Fly bill:
- Anthropic: ~$0.001 per voice intake extraction; ~$0.005 per VIN OCR
- Twilio: $0.0079 per SMS, $0.0085/min per voice, $1/mo per phone number
- Stripe: 2.9% + 30¢ per transaction (just the standard rate)

A single-dealer pilot doing ~200 SMS + 20 calls / month lands around
**$15-25/mo all-in** before the customer's subscription revenue.

---

## 10. Scaling roadmap (when revenue justifies)

1. **More API capacity**: `fly scale count 3 --app aa-api`
2. **Bigger DB**: `fly pg upgrade --vm-size shared-cpu-2x` then
   `--volume-size 50`
3. **Redis** for rate-limit + cache (Upstash on Fly is one-line) —
   required before scaling the scheduler beyond 1
4. **Cloudflare** in front of `app.autoacquisition.io` for caching +
   WAF + DDoS protection
5. **Multi-region** API: pin a Fly region per major metro when
   p99 latency matters (`fly regions add lax sjc dfw --app aa-api`)
6. **Dedicated Postgres**: `fly pg upgrade --vm-size dedicated-cpu-1x`
   when you cross ~50 active dealers
