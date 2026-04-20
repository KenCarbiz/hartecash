/**
 * MV3 service worker. Central place that makes API calls to AutoCurb.
 *
 * Content scripts post WorkerMessage via chrome.runtime.sendMessage; we
 * call the API with the saved settings (dealer id + base URL) and echo
 * the response back.
 */

import { DEFAULTS, type Settings, type WorkerMessage, type WorkerResponse } from "../lib/api";

async function settings(): Promise<Settings> {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return stored as Settings;
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const s = await settings();
  const resp = await fetch(`${s.apiUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Dealer-Id": s.dealerId,
      ...(init.headers ?? {}),
    },
  });
  if (!resp.ok) {
    throw new Error(`${path} -> HTTP ${resp.status}`);
  }
  return (await resp.json()) as T;
}

async function handle(msg: WorkerMessage): Promise<WorkerResponse> {
  try {
    switch (msg.kind) {
      case "ingest": {
        const data = await apiFetch("/sources/extension/ingest", {
          method: "POST",
          body: JSON.stringify({ listing: msg.listing }),
        });
        return { ok: true, data };
      }
      case "ingestBatch": {
        const data = await apiFetch("/sources/extension/ingest/batch", {
          method: "POST",
          body: JSON.stringify({ listings: msg.listings }),
        });
        return { ok: true, data };
      }
      case "lookupByUrl": {
        const data = await apiFetch(
          `/sources/extension/lookup?url=${encodeURIComponent(msg.url)}`,
        );
        return { ok: true, data };
      }
      case "claimLead": {
        const data = await apiFetch("/leads", {
          method: "POST",
          body: JSON.stringify({ listing_id: msg.listingId }),
        });
        return { ok: true, data };
      }
    }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

chrome.runtime.onMessage.addListener((msg: WorkerMessage, _sender, sendResponse) => {
  handle(msg).then(sendResponse);
  return true; // keep the message channel open for async sendResponse
});

// Install default settings on first run.
chrome.runtime.onInstalled.addListener(async () => {
  const existing = await chrome.storage.local.get(DEFAULTS);
  await chrome.storage.local.set({ ...DEFAULTS, ...existing });
});
