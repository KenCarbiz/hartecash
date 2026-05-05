/**
 * MV3 service worker. Central place that makes API calls to AutoAcquisition.
 *
 * Content scripts post WorkerMessage via chrome.runtime.sendMessage; we
 * call the API with the saved settings (Bearer API key when present,
 * X-Dealer-Id header as dev fallback) and echo the response back.
 */

import {
  DEFAULTS,
  type Settings,
  type WorkerMessage,
  type WorkerResponse,
} from "../lib/api";

async function settings(): Promise<Settings> {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return stored as Settings;
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const s = await settings();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  // Prefer Bearer-token auth; fall back to X-Dealer-Id for dev.
  if (s.apiKey) {
    headers["Authorization"] = `Bearer ${s.apiKey}`;
  } else {
    headers["X-Dealer-Id"] = s.dealerId;
  }
  const base = (s.apiUrl || DEFAULTS.apiUrl).replace(/\/$/, "");
  const resp = await fetch(`${base}${path}`, { ...init, headers });
  if (!resp.ok) {
    throw new Error(`${path} -> HTTP ${resp.status}`);
  }
  // 204 = no body. Returning undefined as T is fine for fire-and-forget callers.
  if (resp.status === 204) return undefined as unknown as T;
  return (await resp.json()) as T;
}

/** Increment the all-time counter shown in the popup. */
async function bumpTotal(by: number): Promise<void> {
  if (by <= 0) return;
  const { total_count } = (await chrome.storage.local.get({
    total_count: 0,
  })) as { total_count: number };
  await chrome.storage.local.set({ total_count: (total_count || 0) + by });
}

async function handle(msg: WorkerMessage): Promise<WorkerResponse> {
  try {
    switch (msg.kind) {
      case "ingest": {
        const data = await apiFetch("/sources/extension/ingest", {
          method: "POST",
          body: JSON.stringify({ listing: msg.listing }),
        });
        await bumpTotal(1);
        return { ok: true, data };
      }
      case "ingestBatch": {
        const data = await apiFetch("/sources/extension/ingest/batch", {
          method: "POST",
          body: JSON.stringify({ listings: msg.listings }),
        });
        await bumpTotal(msg.listings.length);
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
      case "telemetry": {
        // Fire-and-forget; we don't want telemetry failures to spam the
        // user's console or block the content script. 204 = no body.
        const manifest = chrome.runtime.getManifest();
        await apiFetch("/telemetry/extension-breakage", {
          method: "POST",
          body: JSON.stringify({
            kind: msg.event,
            url: msg.url,
            user_agent: navigator.userAgent,
            extension_version: manifest.version,
            extra: msg.extra,
          }),
        }).catch(() => undefined);
        return { ok: true };
      }
    }
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    };
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
