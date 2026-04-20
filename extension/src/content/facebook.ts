/**
 * Facebook Marketplace content script.
 *
 * This is the single highest-value piece of AutoCurb. FB Marketplace is
 * the #1 FSBO source by ~5-10x any other single platform, so we harvest
 * aggressively as the dealer browses — but only in THEIR logged-in
 * session, only from pages they chose to view.
 *
 * Two modes:
 *   A) Detail page (/marketplace/item/<id>) — full parse: title, price,
 *      description, images, city. Classify + claim-as-lead overlay.
 *   B) Feed / search page (/marketplace/*, /search, /vehicles, /category)
 *      — harvest every tile the dealer scrolls past. Thin payloads
 *      (title + price + external_id + city + image) fill in when they
 *      later click into a detail page.
 *
 * Feed harvesting prioritizes:
 *   1. GraphQL response intercept (cleanest data; Facebook hydrates
 *      search results from a GraphQL call we can hook on fetch/XHR).
 *   2. DOM tile parse as fallback (works even when GraphQL shape changes).
 *
 * Everything flows through the background service worker so the API key
 * + dealer id stay out of content-script scope.
 */

import { callWorker, type IngestListing } from "../lib/api";

// Debounce + dedupe — Facebook re-renders the same tile many times as
// the dealer scrolls. We cache item_ids we've already sent this page view.
const seenThisSession = new Set<string>();
const pendingBatch: IngestListing[] = [];
let batchTimer: number | null = null;

function flushBatch(): void {
  if (pendingBatch.length === 0) return;
  const copy = pendingBatch.splice(0, pendingBatch.length);
  void callWorker({ kind: "ingestBatch", listings: copy });
}

function queueIngest(listing: IngestListing): void {
  if (!listing.external_id || seenThisSession.has(listing.external_id)) return;
  seenThisSession.add(listing.external_id);
  pendingBatch.push(listing);
  if (batchTimer !== null) return;
  batchTimer = window.setTimeout(() => {
    batchTimer = null;
    flushBatch();
  }, 1500);
  if (pendingBatch.length >= 40) {
    if (batchTimer) window.clearTimeout(batchTimer);
    batchTimer = null;
    flushBatch();
  }
}

// --------------------------------------------------------------------------
// MODE A — detail page (/marketplace/item/<id>)
// --------------------------------------------------------------------------

function isItemPage(): boolean {
  return /\/marketplace\/item\/(\d+)/.test(location.pathname);
}

function itemIdFromUrl(): string | null {
  const m = location.pathname.match(/\/marketplace\/item\/(\d+)/);
  return m ? m[1] : null;
}

interface ParsedDetail {
  external_id: string;
  title: string;
  price: number | null;
  description: string;
  city: string | null;
  images: string[];
}

function parseDetail(): ParsedDetail | null {
  const id = itemIdFromUrl();
  if (!id) return null;

  const title =
    (document.querySelector<HTMLHeadingElement>("h1")?.textContent ?? "").trim();

  const priceMatch = document.body.innerText.match(/\$[\s]?([\d,]+)(?!\d)/);
  const price = priceMatch ? Number(priceMatch[1].replace(/,/g, "")) : null;

  const description = Array.from(
    document.querySelectorAll("[data-testid='description'], div[dir]"),
  )
    .map((el) => (el as HTMLElement).innerText.trim())
    .filter((t) => t.length > 40)
    .slice(0, 1)
    .join("\n");

  const cityMatch = document.body.innerText.match(/Listed in ([A-Za-z ]+,\s?[A-Z]{2})/);
  const city = cityMatch ? cityMatch[1] : null;

  const images = Array.from(document.querySelectorAll<HTMLImageElement>("img"))
    .map((img) => img.src)
    .filter((src) => src.includes("scontent") && !src.includes("emoji"))
    .slice(0, 8);

  return { external_id: id, title, price, description, city, images };
}

function detailToIngest(p: ParsedDetail): IngestListing {
  const yearMatch = p.title.match(/\b(19[89]\d|20[0-3]\d)\b/);
  const [city, state] = (p.city ?? "").split(",").map((s) => s.trim());
  return {
    source: "facebook_marketplace",
    external_id: p.external_id,
    url: location.href.split("?")[0],
    title: p.title,
    description: p.description,
    year: yearMatch ? Number(yearMatch[1]) : undefined,
    price: p.price ?? undefined,
    city: city || undefined,
    state: state || undefined,
    images: p.images,
  };
}

async function runDetail(): Promise<void> {
  const parsed = parseDetail();
  if (!parsed || !parsed.title) return;

  const resp = await callWorker<{ listing_id: number; duplicate: boolean }>({
    kind: "ingest",
    listing: detailToIngest(parsed),
  });
  if (!resp.ok) return;
  renderOverlay(resp.data?.listing_id ?? null, resp.data?.duplicate ?? false);
}

function renderOverlay(listingId: number | null, duplicate: boolean): void {
  const existing = document.getElementById("autocurb-overlay");
  if (existing) existing.remove();

  const host = document.createElement("div");
  host.id = "autocurb-overlay";
  host.className = "autocurb-overlay";
  host.innerHTML = `
    <div class="autocurb-card">
      <div class="autocurb-header">
        <span class="autocurb-logo">A</span>
        <span>AutoCurb</span>
      </div>
      <div class="autocurb-body">
        ${
          duplicate
            ? `<p class="autocurb-dup">Already in your feed · #${listingId ?? "?"}</p>`
            : '<p class="autocurb-status">Indexed in your feed</p>'
        }
        <div class="autocurb-actions">
          <button data-action="claim" class="autocurb-btn autocurb-btn-primary">
            Claim as lead
          </button>
          <button data-action="open" class="autocurb-btn autocurb-btn-secondary">
            Open in AutoCurb
          </button>
        </div>
      </div>
    </div>`;

  document.body.appendChild(host);
  host
    .querySelector<HTMLButtonElement>('[data-action="claim"]')
    ?.addEventListener("click", async () => {
      if (!listingId) return;
      const resp = await callWorker({ kind: "claimLead", listingId });
      if (resp.ok) {
        host.querySelector(".autocurb-status, .autocurb-dup")!.textContent =
          "✓ Lead claimed";
      }
    });
  host
    .querySelector<HTMLButtonElement>('[data-action="open"]')
    ?.addEventListener("click", async () => {
      const { apiUrl } = (await chrome.storage.local.get({ apiUrl: "" })) as {
        apiUrl: string;
      };
      const dashUrl = apiUrl.replace(":8000", ":3000");
      if (listingId) window.open(`${dashUrl}/listings/${listingId}`, "_blank");
    });
}

// --------------------------------------------------------------------------
// MODE B — feed / search pages — the 80% path
// --------------------------------------------------------------------------

function isFeedPage(): boolean {
  if (isItemPage()) return false;
  return (
    location.pathname.startsWith("/marketplace") &&
    !location.pathname.startsWith("/marketplace/you/")
  );
}

/** Inject a page-level script that hooks window.fetch so we can observe
 * GraphQL responses. Content scripts run in an isolated world and can't
 * patch the page's window, so we inject a <script> into the DOM. */
function installGraphQLHook(): void {
  if (document.getElementById("autocurb-gql-hook")) return;
  const code = `(() => {
    const orig = window.fetch;
    window.fetch = async function(input, init) {
      const resp = await orig.apply(this, arguments);
      try {
        const url = (typeof input === 'string' ? input : input.url) || '';
        if (url.includes('/api/graphql/') && init && init.body) {
          const bodyText = typeof init.body === 'string' ? init.body : '';
          if (/marketplace/i.test(bodyText)) {
            const cloned = resp.clone();
            cloned.text().then((txt) => {
              window.postMessage({ __autocurb_gql: true, body: txt.slice(0, 500000) }, '*');
            }).catch(() => {});
          }
        }
      } catch (_e) {}
      return resp;
    };
  })();`;
  const s = document.createElement("script");
  s.id = "autocurb-gql-hook";
  s.textContent = code;
  (document.head || document.documentElement).appendChild(s);
  s.remove();
}

/** Listen for messages posted by the injected hook. */
function listenForGraphQL(): void {
  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const data = event.data as { __autocurb_gql?: boolean; body?: string };
    if (!data || !data.__autocurb_gql || !data.body) return;
    parseGraphQLPayload(data.body);
  });
}

function parseGraphQLPayload(body: string): void {
  // FB's GraphQL responses are multi-JSON-line or single JSON. Parse each
  // chunk and walk the payload for Marketplace product-ish shapes.
  for (const line of body.split("\n")) {
    let obj: unknown;
    try {
      obj = JSON.parse(line);
    } catch {
      continue;
    }
    walkForListings(obj);
  }
}

/** Recursively look for anything that looks like a Marketplace listing. */
function walkForListings(obj: unknown, depth = 0): void {
  if (depth > 10 || obj === null || typeof obj !== "object") return;

  if (Array.isArray(obj)) {
    for (const item of obj) walkForListings(item, depth + 1);
    return;
  }

  const rec = obj as Record<string, unknown>;

  // Facebook Marketplace listing shape: has an `id` + `listing_price` +
  // `marketplace_listing_title` + `primary_listing_photo`.
  const id = rec.id || rec.marketplace_listing_id || rec.listing_id;
  const title =
    rec.marketplace_listing_title ||
    rec.title ||
    (rec.custom_title as string | undefined);
  const priceObj = rec.listing_price || rec.price || rec.formatted_price;
  const looksLikeListing =
    typeof id === "string" &&
    typeof title === "string" &&
    priceObj !== undefined;

  if (looksLikeListing) {
    const extId = String(id);
    if (!seenThisSession.has(extId)) {
      queueIngest(fbGraphToIngest(extId, rec));
    }
  }

  for (const key in rec) walkForListings(rec[key], depth + 1);
}

function fbGraphToIngest(id: string, rec: Record<string, unknown>): IngestListing {
  const title = String(
    rec.marketplace_listing_title || rec.title || rec.custom_title || "",
  );
  const priceObj = (rec.listing_price || rec.price) as
    | { amount?: string | number; amount_with_offset_in_currency?: string; formatted_amount?: string }
    | undefined;
  let price: number | undefined;
  if (priceObj) {
    const raw =
      priceObj.amount ??
      priceObj.amount_with_offset_in_currency ??
      priceObj.formatted_amount;
    const parsed = Number(String(raw).replace(/[^0-9.]/g, ""));
    if (Number.isFinite(parsed) && parsed > 0) price = parsed;
  }
  const photo = rec.primary_listing_photo as
    | { image?: { uri?: string } }
    | undefined;
  const image = photo?.image?.uri;

  const location = (rec.location as { reverse_geocode?: { city?: string; state?: string } } | undefined)?.reverse_geocode;

  const yearMatch = title.match(/\b(19[89]\d|20[0-3]\d)\b/);

  return {
    source: "facebook_marketplace",
    external_id: id,
    url: `https://www.facebook.com/marketplace/item/${id}`,
    title,
    price,
    year: yearMatch ? Number(yearMatch[1]) : undefined,
    city: location?.city,
    state: location?.state,
    images: image ? [image] : [],
  };
}

/** DOM fallback: parse the feed tiles directly. FB often lazy-renders them. */
function parseFeedTiles(): void {
  // Feed tile anchors all link to /marketplace/item/<id>
  const anchors = document.querySelectorAll<HTMLAnchorElement>(
    'a[href*="/marketplace/item/"]',
  );
  anchors.forEach((a) => {
    const href = a.href;
    const m = href.match(/\/marketplace\/item\/(\d+)/);
    if (!m) return;
    const id = m[1];
    if (seenThisSession.has(id)) return;

    // Walk up the anchor's card to collect visible text.
    const card = a.closest("div") || a;
    const text = card.textContent ?? "";
    const priceMatch = text.match(/\$[\s]?([\d,]+)(?!\d)/);
    const price = priceMatch ? Number(priceMatch[1].replace(/,/g, "")) : undefined;
    const title = (a.textContent ?? "").trim().slice(0, 200) || undefined;
    const yearMatch = title?.match(/\b(19[89]\d|20[0-3]\d)\b/);
    const img = card.querySelector<HTMLImageElement>("img[src*='scontent']");

    queueIngest({
      source: "facebook_marketplace",
      external_id: id,
      url: `https://www.facebook.com/marketplace/item/${id}`,
      title,
      price,
      year: yearMatch ? Number(yearMatch[1]) : undefined,
      images: img?.src ? [img.src] : [],
    });
  });
}

function installFeedObserver(): void {
  // Kick once on load, then re-run on any DOM mutation (infinite scroll).
  parseFeedTiles();
  const obs = new MutationObserver(() => {
    parseFeedTiles();
  });
  obs.observe(document.body, { childList: true, subtree: true });
}

// --------------------------------------------------------------------------
// Router
// --------------------------------------------------------------------------

async function route(): Promise<void> {
  if (isItemPage()) {
    await runDetail();
  } else if (isFeedPage()) {
    installGraphQLHook();
    installFeedObserver();
  }
}

let lastPath = location.pathname;
setInterval(() => {
  if (location.pathname !== lastPath) {
    lastPath = location.pathname;
    seenThisSession.clear();
    void route();
  }
}, 1200);

// Flush any pending batch on page hide.
window.addEventListener("pagehide", () => flushBatch(), { capture: true });

listenForGraphQL();
void route();
