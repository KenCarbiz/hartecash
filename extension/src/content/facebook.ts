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
  // Jittered debounce: random 1.0-2.5s window. Looks more human and
  // avoids consistent timing fingerprints if FB ever bothers profiling us.
  const delay = 1000 + Math.floor(Math.random() * 1500);
  batchTimer = window.setTimeout(() => {
    batchTimer = null;
    flushBatch();
  }, delay);
  if (pendingBatch.length >= 40) {
    if (batchTimer) window.clearTimeout(batchTimer);
    batchTimer = null;
    flushBatch();
  }
}

/** Refuse to do anything when FB has presented a security challenge.
 *  Posting telemetry here would just compound the problem. */
function isCheckpointed(): boolean {
  if (location.pathname.startsWith("/checkpoint/")) return true;
  if (location.pathname.startsWith("/login")) return true;
  // FB sometimes flashes "Help us confirm it's you" inline on a Marketplace
  // route without changing the URL. Cheap DOM check for the title text.
  const t = document.title.toLowerCase();
  if (t.includes("security check") || t.includes("confirm it's you")) {
    return true;
  }
  return false;
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

// Marker substrings that have to appear in a GraphQL response body for
// us to bother walking it. Skipping non-marketplace payloads (Messenger
// chat, news feed, notifications) cuts CPU and avoids accidentally
// matching unrelated id/title/price triples in chat data.
const MARKETPLACE_MARKERS = [
  "marketplace_listing_id",
  "marketplace_listing_title",
  "marketplace_feed_stories",
  "MarketplaceListing",
];

function parseGraphQLPayload(body: string): void {
  // Cheap pre-filter — skip Messenger / News Feed / Notifications GraphQL.
  if (!MARKETPLACE_MARKERS.some((m) => body.includes(m))) return;
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
  if (isCheckpointed()) {
    // FB has thrown up a verification wall; back off completely.
    return;
  }
  // GraphQL hook runs on ANY Marketplace page — FB's SPA may load feed
  // data even when the URL currently shows a detail page.
  installGraphQLHook();

  if (isItemPage()) {
    await runDetail();
  } else if (isFeedPage()) {
    installFeedObserver();
    scheduleBreakageCheck();
    void maybeStartAutoScroll();
  }
}

/** Opt-in auto-scroll: when the dealer enabled it in the popup, slowly
 *  scroll the marketplace feed so more tiles enter the harvester's
 *  view. Stops on tab blur, on URL change, when bottom is reached,
 *  or after 8 minutes (safety cap). Jittered 4-9s between scrolls. */
let autoScrollAbort: (() => void) | null = null;
async function maybeStartAutoScroll(): Promise<void> {
  if (autoScrollAbort) {
    autoScrollAbort();
    autoScrollAbort = null;
  }
  const { autoScroll } = (await chrome.storage.local.get({ autoScroll: false })) as {
    autoScroll: boolean;
  };
  if (!autoScroll) return;

  let stopped = false;
  let timer: number | null = null;
  const startedAt = Date.now();
  const MAX_RUN_MS = 8 * 60 * 1000;
  const startedPath = location.pathname;

  const stop = () => {
    if (stopped) return;
    stopped = true;
    if (timer) window.clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVis);
  };
  const onVis = () => {
    if (document.hidden) stop();
  };
  document.addEventListener("visibilitychange", onVis);

  const tick = () => {
    if (stopped) return;
    if (location.pathname !== startedPath) return stop();
    if (Date.now() - startedAt > MAX_RUN_MS) return stop();
    const remaining =
      document.documentElement.scrollHeight -
      window.scrollY -
      window.innerHeight;
    if (remaining < 80) return stop(); // hit bottom
    const step = 600 + Math.floor(Math.random() * 400); // 600-1000 px
    window.scrollBy({ top: step, behavior: "smooth" });
    const wait = 4000 + Math.floor(Math.random() * 5000); // 4-9 s
    timer = window.setTimeout(tick, wait);
  };
  // Initial delay so we don't scroll mid-page-render.
  timer = window.setTimeout(tick, 2500);
  autoScrollAbort = stop;
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
    if (autoScrollAbort) {
      autoScrollAbort();
      autoScrollAbort = null;
    }
    void route();
  }
}, 1200);

// Flush any pending batch on page hide.
window.addEventListener("pagehide", () => flushBatch(), { capture: true });

listenForGraphQL();
void route();
