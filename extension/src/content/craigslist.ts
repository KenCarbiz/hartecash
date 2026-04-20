/**
 * Craigslist content script.
 *
 * We already scrape Craigslist server-side via RSS, so this script only
 * *looks up* the current listing and shows the overlay with prior-engagement
 * info — it doesn't need to re-ingest.
 */

import { callWorker } from "../lib/api";

function renderOverlay(listingId: number | null, duplicate: boolean) {
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
            ? `<p class="autocurb-dup">Already in your feed · #${listingId}</p>`
            : '<p class="autocurb-status">Not yet indexed — your next poll will pick it up</p>'
        }
        ${
          listingId
            ? `<div class="autocurb-actions">
                 <button data-action="claim" class="autocurb-btn autocurb-btn-primary">Claim as lead</button>
                 <button data-action="open" class="autocurb-btn autocurb-btn-secondary">Open in AutoCurb</button>
               </div>`
            : ""
        }
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
      const dashUrl = apiUrl.replace(":8000", ":3000");
      if (listingId) window.open(`${dashUrl}/listings/${listingId}`, "_blank");
    },
  );
}

async function run() {
  const resp = await callWorker<{ listing_id: number | null; duplicate: boolean }>({
    kind: "lookupByUrl",
    url: location.href.split("?")[0],
  });
  if (resp.ok) {
    renderOverlay(resp.data?.listing_id ?? null, resp.data?.duplicate ?? false);
  }
}

void run();
