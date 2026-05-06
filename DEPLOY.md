# Deploying AutoAcquisition

Step-by-step playbook to take this repo from "tests pass on my
machine" to a public URL your dealership can sign in to. Three
services to ship: the **API**, the **scheduler** (background workers),
and the **dashboard**. Plus the **Chrome extension** to the Web Store.

> **Time budget**: ~45 min hands-on for the first three services.
> Plus 2-7 days for Google to review the Chrome extension.

---

## 0 — Prerequisites (one-time)

Make these accounts before you start:

| Account | Why | Cost |
|---|---|---|
| [Fly.io](https://fly.io/app/sign-up) | Hosts the API + scheduler | Free tier covers MVP; ~$5/mo for the DB |
| [Vercel](https://vercel.com/signup) | Hosts the Next.js dashboard | Free hobby tier is fine |
| [Anthropic Console](https://console.anthropic.com/) | Claude key for AI vision | Pay-as-you-go (~$0.005/listing) |
| [Chrome Web Store Developer](https://chrome.google.com/webstore/devconsole/) | Publishes the extension | One-time $5 |
| Domain registrar (Namecheap / Cloudflare) | `autoacquisition.io` for branded URLs | ~$30/yr |

Install + sign in to the CLIs:

```bash
# Fly
curl -L https://fly.io/install.sh | sh
fly auth login

# Vercel
npm i -g vercel
vercel login
```

---

## 1 — Backend API → Fly.io (~15 min)

Lives in `fsbo-data-platform/`. Already has a working `fly.toml` and
`Dockerfile`.

### 1a. Create the Fly app

```bash
cd fsbo-data-platform
fly launch --no-deploy --copy-config --dockerfile Dockerfile \
  --name autoacquisition-api
```

When prompted:
- Region → `iad` (or whatever's closest to your dealership)
- Postgres → **No** (we'll create it explicitly so the name is right)
- Redis → **No**
- Deploy now → **No**

### 1b. Create + attach Postgres

```bash
fly postgres create --name autoacquisition-db --region iad \
  --vm-size shared-cpu-1x --volume-size 10
fly postgres attach autoacquisition-db --app autoacquisition-api
```

The attach command sets `DATABASE_URL` as a secret automatically.

### 1c. Set production secrets

```bash
fly secrets set --app autoacquisition-api \
  ENV_MODE=production \
  COOKIE_SECURE=true \
  JWT_SECRET=$(openssl rand -hex 32) \
  COOKIE_DOMAIN=.autoacquisition.io \
  APP_ORIGIN=https://app.autoacquisition.io \
  ANTHROPIC_API_KEY=sk-ant-...
```

If you have SendGrid + Twilio:
```bash
fly secrets set --app autoacquisition-api \
  EMAIL_BACKEND=sendgrid \
  SENDGRID_API_KEY=SG.your_key \
  EMAIL_FROM=noreply@autoacquisition.io \
  EMAIL_FROM_NAME="AutoAcquisition" \
  TWILIO_ACCOUNT_SID=AC... \
  TWILIO_AUTH_TOKEN=... \
  TWILIO_MESSAGING_SERVICE_SID=MG...
```

> **JWT_SECRET is non-negotiable.** The API refuses to boot in
> production with the dev default. The startup check fails loud.

### 1d. Deploy

```bash
fly deploy --app autoacquisition-api
```

The Dockerfile runs `alembic upgrade head` as a release command, so
all 23 migrations run automatically on first boot. Watch the logs:

```bash
fly logs --app autoacquisition-api
```

Expected: `Uvicorn running on http://0.0.0.0:8000` and a 200 on
`/health`. Hit it in your browser:

```
https://autoacquisition-api.fly.dev/health
# -> {"status": "ok"}
```

---

## 2 — Scheduler (background workers) → Fly.io (~5 min)

Same Docker image, different process. Runs craigslist polls, photo
mirror catch-up, lead-alert mailer, daily rescore.

```bash
cd fsbo-data-platform
fly launch --no-deploy --copy-config --config fly.scheduler.toml \
  --dockerfile Dockerfile --name autoacquisition-scheduler
fly postgres attach autoacquisition-db --app autoacquisition-scheduler
fly secrets set --app autoacquisition-scheduler \
  ANTHROPIC_API_KEY=sk-ant-... \
  EMAIL_BACKEND=sendgrid \
  SENDGRID_API_KEY=SG.your_key \
  APP_ORIGIN=https://app.autoacquisition.io
fly deploy --config fly.scheduler.toml --app autoacquisition-scheduler
```

> **Scale it to exactly one instance.** The token-bucket rate limiter
> is in-process; running multiple would double-poll every source.

```bash
fly scale count 1 --app autoacquisition-scheduler
fly logs --app autoacquisition-scheduler
```

Expected: a `scheduler.start` log line, then periodic
`craigslist.fetch` entries every few minutes.

---

## 3 — Dashboard → Vercel (~5 min)

Next.js 15 in `web/`. Vercel handles this faster than Fly.

### 3a. Connect the repo

1. Go to [vercel.com/new](https://vercel.com/new)
2. **Import** `KenCarbiz/hartecash`
3. Configure:
   - **Root Directory**: `web` (critical — repo is a monorepo)
   - **Framework Preset**: Next.js (auto-detected)
   - leave Build Command + Output Directory at defaults
4. **Environment Variables**:
   ```
   FSBO_API_URL=https://autoacquisition-api.fly.dev
   ```
5. Click **Deploy**.

First build takes ~3 minutes. You'll get a URL like
`autoacquisition-yourorg.vercel.app`.

### 3b. Smoke test the dashboard

Open the Vercel URL → land on the login page. Click **Create
account**, register with your email + a dealer name. Session
redirects to `/`.

Visit `/settings` → you see your dealer ID + the **Generate install
code** button. That confirms the dashboard talks to the API.

### 3c. Add the custom domain

In **Vercel**: Project → Settings → Domains → add
`app.autoacquisition.io`.

In your registrar (Cloudflare / Namecheap / etc.):
- Add `CNAME` record: `app` → `cname.vercel-dns.com.`
- Wait ~5 min for DNS. Vercel issues a Let's Encrypt cert
  automatically.

You also want the **API** on a branded subdomain so cookies work
across origins. In Fly:

```bash
fly certs create api.autoacquisition.io --app autoacquisition-api
fly certs show api.autoacquisition.io --app autoacquisition-api
# follow the DNS instructions Fly prints — usually a CNAME or A+AAAA pair
```

Then in Vercel update `FSBO_API_URL` to
`https://api.autoacquisition.io` and redeploy.

---

## 4 — Chrome extension → Web Store (~10 min hands-on, 2-7 days review)

### 4a. Update the production API URL

The extension's dev defaults point at `localhost`. Edit
`extension/src/lib/api.ts`:

```ts
export const DEFAULTS: Settings = {
  apiUrl: "https://api.autoacquisition.io", // was http://localhost:8000
  dealerId: "",                              // was "demo-dealer"
  apiKey: "",
  userLabel: "me",
  autoScroll: false,
};
```

Commit + push:
```bash
git add extension/src/lib/api.ts
git commit -m "Extension: point production defaults at api.autoacquisition.io"
git push origin main
```

### 4b. Build the production bundle

```bash
cd extension
npm install
npm run build
```

Output: `extension/dist/`.

### 4c. Smoke test locally before submitting

1. Open `chrome://extensions` → toggle **Developer mode** on.
2. Click **Load unpacked** → select `extension/dist/`.
3. Open the popup → it shows the **Connect this extension** card.
4. In another tab open `https://app.autoacquisition.io/settings` →
   click **Generate install code** → copy the 8-char code.
5. Back in the popup → paste the code → click **Connect**. The
   card should disappear and the connection dot should go green.
6. Open Facebook Marketplace → scroll a few car listings.
7. Within ~10 sec they appear in your dashboard at `/listings`.
8. Click into one listing → the AI condition panel shows "Claude
   vision running…" and fills in within ~30 sec.

If steps 6-8 work, you're ready to ship.

### 4d. Package + submit

```bash
cd extension/dist
zip -r ../autoacquisition.zip .
```

At [chrome.google.com/webstore/devconsole](https://chrome.google.com/webstore/devconsole):

1. Pay the one-time $5 developer fee.
2. **New item** → upload `extension/autoacquisition.zip`.
3. Fill in the listing using copy from
   `extension/CHROME_STORE_LISTING.md` (already drafted).
4. **Privacy policy URL**: host `extension/PRIVACY.md` somewhere
   public. Easiest path: paste it as a Next.js page at
   `app.autoacquisition.io/privacy` and use that URL.
5. **Single purpose** + **permissions justification** paragraphs:
   paste from `CHROME_STORE_LISTING.md`.
6. Submit.

Google review usually takes 2-4 business days.

### 4e. Pushing extension updates later

```bash
# bump version field in extension/manifest.json + extension/package.json
cd extension && npm run build
cd dist && zip -r ../autoacquisition-vX.zip .
# upload to Web Store dashboard → Package → Upload new package
```

Chrome auto-updates installed extensions within ~6 hours.

---

## 5 — First-deploy verification checklist

Run through this once you finish steps 1-3:

- [ ] `https://api.autoacquisition.io/health` → `{"status":"ok"}`
- [ ] `https://app.autoacquisition.io/` redirects to `/login`
- [ ] You can register, log in, and see your dealer ID in `/settings`
- [ ] `/sources` shows craigslist firing (give the scheduler 5 min)
- [ ] Generate an install code → paste into the loaded extension →
      browse Marketplace → listings appear in `/listings` within 10 sec
- [ ] Open a listing → vehicle box renders the structured stack;
      **AI condition** panel fills in within ~30 sec (needs
      `ANTHROPIC_API_KEY`)
- [ ] Send yourself an SMS via `ComposePanel` — Twilio status webhook
      hits `/webhooks/twilio/status` (visible in `fly logs`)

---

## 6 — Day-2 ops cheatsheet

```bash
# Tail logs
fly logs --app autoacquisition-api
fly logs --app autoacquisition-scheduler
vercel logs <your-vercel-project>

# Open a Postgres shell
fly postgres connect --app autoacquisition-db

# Run a one-off rescore
curl -X POST https://api.autoacquisition.io/admin/rescore \
  -H "Authorization: Bearer ac_live_..."

# Roll back a bad API deploy
fly releases --app autoacquisition-api
fly deploy --app autoacquisition-api \
  --image registry.fly.io/autoacquisition-api:deployment-<id>

# Bump the dashboard
git push origin main   # Vercel auto-deploys

# Rotate JWT secret (forces logout for everyone)
fly secrets set --app autoacquisition-api JWT_SECRET=$(openssl rand -hex 32)
```

---

## 7 — Common first-deploy gotchas

**API boots and immediately exits with `JWT_SECRET must be set`** —
You forgot step 1c. Set the secret and redeploy.

**Dashboard shows "Can't reach the FSBO API"** —
Vercel `FSBO_API_URL` env var isn't set, or it points at a hostname
DNS hasn't propagated yet. Check `Settings → Environment Variables`
and redeploy.

**Cookies don't persist across login** —
`COOKIE_DOMAIN` on the API doesn't match the dashboard's domain. They
must share a parent — e.g. `.autoacquisition.io` if dashboard is on
`app.autoacquisition.io` and API is on `api.autoacquisition.io`.

**Extension shows "Can't reach API"** —
The extension's `apiUrl` in storage is still `http://localhost:8000`
(set during dev). Open the popup → Settings → change to
`https://api.autoacquisition.io` → Save.

**Scheduler runs everything twice** —
You scaled the scheduler app past 1. Run
`fly scale count 1 --app autoacquisition-scheduler`.

**Photos 404 on the listing detail page** —
Fly's filesystem is ephemeral. The current photo-mirror writes to
local disk, which is fine for a single API instance but lost on
deploy. Move to S3-compatible storage when you scale past one
machine — see `fsbo/media/mirror.py:MIRROR_ROOT`.

---

## 8 — Scaling notes (when you outgrow MVP)

- **API** is stateless; horizontally scale behind Fly's load balancer.
- **Scheduler** stays at exactly 1 until you migrate the in-process
  token-bucket to Redis. Running >1 = double-polls every source.
- **Photo mirror** moves from local FS to S3 (Cloudflare R2 is
  cheapest) when you go multi-replica. Storage abstraction is
  intentionally narrow in `fsbo.media.mirror` — swap the backend
  behind the same `mirror_one(url) -> key` contract.
- **Postgres** indexes are tuned for ~100k listings. Add a GIN index
  on `listings.description` once you cross ~5M rows and full-text
  search latency hurts.

---

## 9 — Security pre-launch checklist

- [ ] `ENV_MODE=production` set on the API
- [ ] `JWT_SECRET` rotated from the default 32+ byte value
- [ ] `COOKIE_SECURE=true`
- [ ] TLS everywhere (Fly + Vercel both auto-issue certs)
- [ ] Postgres not exposed to public internet (Fly default is private)
- [ ] API keys stored hashed (already done — `ApiKey.token_hash`)
- [ ] A2P 10DLC brand + campaign registered with Twilio before
      sending SMS at any volume
- [ ] Privacy policy + terms of service published at
      `app.autoacquisition.io/privacy` + `/terms`
- [ ] Legal review of scraping sources before enabling each (RSS for
      Craigslist is fine; check per-source notes in `sources/*.py`)
