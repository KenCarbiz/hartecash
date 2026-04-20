/**
 * Facebook Marketplace content script.
 *
 * FB's DOM is aggressively randomized and hydrated from GraphQL. We use
 * a defensive, multi-strategy extractor and only fire on listing detail
 * pages (/marketplace/item/<id>). Search-result scraping is deliberately
 * excluded to stay close to "this is just augmenting the user's view."
 */

import { callWorker, type IngestListing } from "../lib/api";

interface ParsedListing {
  external_id: string;
  title: string;
  price: number | null;
  description: string;
  city: string | null;
  images: string[];
  postedAt: string | null;
}

function isItemPage(): boolean {
  return /\/marketplace\/item\/(\d+)/.test(location.pathname);
}

function itemIdFromUrl(): string | null {
  const m = location.pathname.match(/\/marketplace\/item\/(\d+)/);
  return m ? m[1] : null;
}

function parse(): ParsedListing | null {
  const id = itemIdFromUrl();
  if (!id) return null;

  const title =
    (document.querySelector<HTMLHeadingElement>("h1")?.textContent ?? "").trim();

  // FB renders price as e.g. "$12,500" in an aria-label or visible text. We
  // look for anything that looks like a USD price near the title.
  const priceMatch = document.body.innerText.match(/\$[\s]?([\d,]+)(?!\d)/);
  const price = priceMatch ? Number(priceMatch[1].replace(/,/g, "")) : null;

  // Description: FB collapses long descriptions behind a "See more" button.
  // We grab the visible description block; content script runs at document_idle
  // so most of the page is hydrated.
  const description = Array.from(document.querySelectorAll("[data-testid='description'], div[dir]"))
    .map((el) => (el as HTMLElement).innerText.trim())
    .filter((t) => t.length > 40)
    .slice(0, 1)
    .join("\n");

  // City lookup: FB usually shows "Listed in <City, ST>" somewhere near the
  // breadcrumb. This is best-effort.
  const cityMatch = document.body.innerText.match(/Listed in ([A-Za-z ]+,\s?[A-Z]{2})/);
  const city = cityMatch ? cityMatch[1] : null;

  const images = Array.from(document.querySelectorAll<HTMLImageElement>("img"))
    .map((img) => img.src)
    .filter((src) => src.includes("scontent") && !src.includes("emoji"))
    .slice(0, 8);

  return {
    external_id: id,
    title,
    price,
    description,
    city,
    images,
    postedAt: null,
  };
}

function toIngest(parsed: ParsedListing): IngestListing {
  const yearMatch = parsed.title.match(/\b(19[89]\d|20[0-3]\d)\b/);
  const year = yearMatch ? Number(yearMatch[1]) : undefined;
  const [city, state] = (parsed.city ?? "").split(",").map((s) => s.trim());
  return {
    source: "facebook_marketplace",
    external_id: parsed.external_id,
    url: location.href.split("?")[0],
    title: parsed.title,
    description: parsed.description,
    year,
    price: parsed.price ?? undefined,
    city: city || undefined,
    state: state || undefined,
    images: parsed.images,
    posted_at: parsed.postedAt ?? undefined,
  };
}

function renderOverlay(listingId: number | null, duplicate: boolean): HTMLElement {
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
  host.querySelector<HTMLButtonElement>('[data-action="claim"]')?.addEventListener(
    "click",
    async () => {
      if (!listingId) return;
      const resp = await callWorker({ kind: "claimLead", listingId });
      if (resp.ok) host.querySelector(".autocurb-status, .autocurb-dup")!.textContent =
        "✓ Lead claimed";
    },
  );
  host.querySelector<HTMLButtonElement>('[data-action="open"]')?.addEventListener(
    "click",
    async () => {
      const { apiUrl } = (await chrome.storage.local.get({ apiUrl: "" })) as {
        apiUrl: string;
      };
      // apiUrl is the data service; the dashboard is the web app. Both may
      // share a base host in prod; for dev we fall back to localhost:3000.
      const dashUrl = apiUrl.replace(":8000", ":3000");
      if (listingId) window.open(`${dashUrl}/listings/${listingId}`, "_blank");
    },
  );

  return host;
}

async function run() {
  if (!isItemPage()) return;
  const parsed = parse();
  if (!parsed || !parsed.title) return;

  const ingestResp = await callWorker<{ listing_id: number; duplicate: boolean }>({
    kind: "ingest",
    listing: toIngest(parsed),
  });
  if (!ingestResp.ok) return;
  renderOverlay(ingestResp.data?.listing_id ?? null, ingestResp.data?.duplicate ?? false);
}

// Re-run on SPA navigation — Facebook uses pushState.
let lastPath = location.pathname;
setInterval(() => {
  if (location.pathname !== lastPath) {
    lastPath = location.pathname;
    void run();
  }
}, 1200);

void run();
