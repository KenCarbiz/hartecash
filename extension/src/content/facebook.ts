/**
 * Facebook Marketplace content script.
 *
 * This is the single highest-value piece of AutoAcquisition. FB Marketplace is
 * the #1 FSBO source by ~5-10x any other single platform, so we harvest
 * aggressively as the dealer browses — but only in THEIR logged-in
 * session, only from pages they chose to view.
 *
 * Two modes:
 *   A) Detail page (/marketplace/item/<id>) — full parse: title, price,
 *      description, mileage, images, city. Classify + claim-as-lead overlay.
 *   B) Feed / search page (/marketplace/*, /search, /vehicles, /category)
 *      — harvest every tile the dealer scrolls past. Thin payloads
 *      (title + price + mileage + external_id + city + image) fill in
 *      when they later click into a detail page.
 *
 * Feed harvesting uses three complementary strategies:
 *   1. window.fetch hook  — cleanest data; FB hydrates search results via
 *      `/api/graphql/` POSTs we can observe and walk for listing shapes.
 *   2. XMLHttpRequest hook — older code paths + FB's messenger plus a
 *      handful of GraphQL endpoints still use XHR; same walker works.
 *   3. MutationObserver DOM tile parse — fallback that works even when
 *      FB restructures their GraphQL shape.
 *
 * Everything flows through the background service worker so the API key
 * + dealer id stay out of content-script scope.
 */

import { callWorker, type IngestListing } from "../lib/api";
import {
  bestImageFromTile,
  extractCityState,
  extractMileage,
  extractPrice,
  extractYear,
  graphRecordToIngest,
  upgradeImageUrl,
  walkForListingRecords,
} from "./parsers";

// Debounce + dedupe — Facebook re-renders the same tile many times as
// the dealer scrolls. We cache item_ids we've already sent this page view.
const seenThisSession = new Set<string>();
const pendingBatch: IngestListing[] = [];
let batchTimer: number | null = null;
let sessionCount = 0;

function bumpCounter(): void {
  sessionCount += 1;
  // Best-effort persistence; swallow errors.
  chrome.storage.session?.set?.({ session_count: sessionCount });
}

function flushBatch(): void {
  if (pendingBatch.length === 0) return;
  const copy = pendingBatch.splice(0, pendingBatch.length);
  void callWorker({ kind: "ingestBatch", listings: copy });
}

function queueIngest(listing: IngestListing): void {
  if (!listing.external_id || seenThisSession.has(listing.external_id)) return;
  seenThisSession.add(listing.external_id);
  pendingBatch.push(listing);
  bumpCounter();
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
  price: number | undefined;
  description: string;
  mileage: number | undefined;
  cityState: { city: string; state: string } | undefined;
  images: string[];
}

function parseDetail(): ParsedDetail | null {
  const id = itemIdFromUrl();
  if (!id) return null;

  const title =
    (document.querySelector<HTMLHeadingElement>("h1")?.textContent ?? "").trim();

  const bodyText = document.body.innerText;
  const price = extractPrice(bodyText);
  const mileage = extractMileage(bodyText);
  const cityState = extractCityState(bodyText);

  const description = Array.from(
    document.querySelectorAll("[data-testid='description'], div[dir]"),
  )
    .map((el) => (el as HTMLElement).innerText.trim())
    .filter((t) => t.length > 40)
    .slice(0, 1)
    .join("\n");

  const images = Array.from(document.querySelectorAll<HTMLImageElement>("img"))
    .map((img) => img.src)
    .filter((src) => src && !src.includes("emoji"))
    .filter((src) => src.includes("scontent") || src.includes("fbcdn"))
    .map(upgradeImageUrl)
    .slice(0, 8);

  return { external_id: id, title, price, description, mileage, cityState, images };
}

function detailToIngest(p: ParsedDetail): IngestListing {
  return {
    source: "facebook_marketplace",
    external_id: p.external_id,
    url: location.href.split("?")[0],
    title: p.title,
    description: p.description,
    year: extractYear(p.title),
    price: p.price,
    mileage: p.mileage,
    city: p.cityState?.city,
    state: p.cityState?.state,
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
  const existing = document.getElementById("autoacquisition-overlay");
  if (existing) existing.remove();

  const host = document.createElement("div");
  host.id = "autoacquisition-overlay";
  host.className = "autoacquisition-overlay";
  host.innerHTML = `
    <div class="autoacquisition-card">
      <div class="autoacquisition-header">
        <span class="autoacquisition-logo">A</span>
        <span>AutoAcquisition</span>
      </div>
      <div class="autoacquisition-body">
        ${
          duplicate
            ? `<p class="autoacquisition-dup">Already in your feed · #${listingId ?? "?"}</p>`
            : '<p class="autoacquisition-status">Indexed in your feed</p>'
        }
        <div class="autoacquisition-actions">
          <button data-action="claim" class="autoacquisition-btn autoacquisition-btn-primary">
            Claim as lead
          </button>
          <button data-action="open" class="autoacquisition-btn autoacquisition-btn-secondary">
            Open in AutoAcquisition
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
        host.querySelector(".autoacquisition-status, .autoacquisition-dup")!.textContent =
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

/** Inject a page-level script that hooks window.fetch + XMLHttpRequest
 * so we can observe Facebook's GraphQL traffic. Content scripts run in
 * an isolated world and can't patch the page's window, so we inject a
 * <script> into the DOM. */
function installGraphQLHook(): void {
  if (document.getElementById("autoacquisition-gql-hook")) return;
  const code = `(() => {
    if (window.__autoacquisitionHooked) return;
    window.__autoacquisitionHooked = true;
    const MARKER = '__autoacquisition_gql';
    const post = (txt) => {
      try {
        window.postMessage({ [MARKER]: true, body: String(txt).slice(0, 800000) }, '*');
      } catch (_e) {}
    };
    const isGql = (url) =>
      typeof url === 'string' && url.indexOf('/api/graphql/') !== -1;

    // fetch hook
    const origFetch = window.fetch;
    window.fetch = async function(input, init) {
      const resp = await origFetch.apply(this, arguments);
      try {
        const url = (typeof input === 'string' ? input : input && input.url) || '';
        if (isGql(url)) {
          const cloned = resp.clone();
          cloned.text().then(post).catch(() => {});
        }
      } catch (_e) {}
      return resp;
    };

    // XHR hook
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url) {
      this.__autoacquisition_url = url;
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
      try {
        if (isGql(this.__autoacquisition_url)) {
          this.addEventListener('load', () => {
            try { post(this.responseText); } catch (_e) {}
          });
        }
      } catch (_e) {}
      return origSend.apply(this, arguments);
    };
  })();`;
  const s = document.createElement("script");
  s.id = "autoacquisition-gql-hook";
  s.textContent = code;
  (document.head || document.documentElement).appendChild(s);
  s.remove();
}

/** Listen for messages posted by the injected hook. */
function listenForGraphQL(): void {
  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const data = event.data as { __autoacquisition_gql?: boolean; body?: string };
    if (!data || !data.__autoacquisition_gql || !data.body) return;
    parseGraphQLPayload(data.body);
  });
}

function parseGraphQLPayload(body: string): void {
  // FB's GraphQL responses are multi-JSON-line or single JSON. Parse each
  // chunk and walk the payload for Marketplace product-ish shapes.
  const lines = body.split("\n").filter(Boolean);
  for (const line of lines) {
    let obj: unknown;
    try {
      obj = JSON.parse(line);
    } catch {
      continue;
    }
    for (const rec of walkForListingRecords(obj)) {
      const ingest = graphRecordToIngest(rec);
      if (ingest) queueIngest(ingest);
    }
  }
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

    // Walk up to the card container that holds the price + city + image.
    const card =
      (a.closest("[role='article']") as HTMLElement | null) ||
      (a.closest("div") as HTMLElement | null) ||
      (a as HTMLElement);
    const text = card.textContent ?? "";
    const price = extractPrice(text);
    const mileage = extractMileage(text);
    const cityState = extractCityState(text);
    const title = (a.textContent ?? "").trim().slice(0, 200) || undefined;
    const image = bestImageFromTile(card);

    queueIngest({
      source: "facebook_marketplace",
      external_id: id,
      url: `https://www.facebook.com/marketplace/item/${id}`,
      title,
      price,
      mileage,
      year: extractYear(title),
      city: cityState?.city,
      state: cityState?.state,
      images: image ? [image] : [],
    });
  });
}

function installFeedObserver(): void {
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
  // GraphQL hook runs on ANY Marketplace page — FB's SPA may load feed
  // data even when the URL currently shows a detail page.
  installGraphQLHook();

  if (isItemPage()) {
    await runDetail();
  } else if (isFeedPage()) {
    installFeedObserver();
    scheduleBreakageCheck();
  }
}

/** When we land on a feed page but harvest 0 listings within the timeout
 *  window, FB has probably changed their GraphQL shape or DOM structure.
 *  Fire telemetry once per route so we find out before dealers do. */
let breakageReported = false;
function scheduleBreakageCheck(): void {
  breakageReported = false;
  const url = location.href;
  setTimeout(() => {
    if (breakageReported) return;
    if (sessionCount > 0) return;
    // Confirm there are tiles on the page — if FB just hasn't rendered
    // yet, skip the report.
    const tileCount = document.querySelectorAll(
      'a[href*="/marketplace/item/"]',
    ).length;
    breakageReported = true;
    void callWorker({
      kind: "telemetry",
      event: tileCount > 0 ? "graphql_walker_empty" : "dom_walker_empty",
      url,
      extra: { tile_count_seen: tileCount, session_count: sessionCount },
    });
  }, 8000);
}

let lastPath = location.pathname;
setInterval(() => {
  if (location.pathname !== lastPath) {
    lastPath = location.pathname;
    seenThisSession.clear();
    sessionCount = 0;
    chrome.storage.session?.set?.({ session_count: 0 });
    void route();
  }
}, 1200);

// Flush any pending batch on page hide.
window.addEventListener("pagehide", () => flushBatch(), { capture: true });

listenForGraphQL();
void route();
