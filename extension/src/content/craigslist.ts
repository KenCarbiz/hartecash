/**
 * Craigslist content script.
 *
 * We already scrape Craigslist server-side via RSS, so this script only
 * *looks up* the current listing and shows the overlay with prior-engagement
 * info — it doesn't need to re-ingest.
 */

import { callWorker } from "../lib/api";

function renderOverlay(listingId: number | null, duplicate: boolean) {
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
            ? `<p class="autoacquisition-dup">Already in your feed · #${listingId}</p>`
            : '<p class="autoacquisition-status">Not yet indexed — your next poll will pick it up</p>'
        }
        ${
          listingId
            ? `<div class="autoacquisition-actions">
                 <button data-action="claim" class="autoacquisition-btn autoacquisition-btn-primary">Claim as lead</button>
                 <button data-action="open" class="autoacquisition-btn autoacquisition-btn-secondary">Open in AutoAcquisition</button>
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
      if (resp.ok) host.querySelector(".autoacquisition-status, .autoacquisition-dup")!.textContent =
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
