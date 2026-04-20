/**
 * Thin client for the AutoCurb API, used by content scripts + background.
 *
 * All extension requests go through the service worker (background) because
 * MV3 content scripts have stricter CORS/cookie constraints. We post messages
 * to the worker; the worker calls the API with the dealer's API key.
 */

export interface IngestListing {
  source: string;
  external_id: string;
  url: string;
  title?: string;
  description?: string;
  year?: number;
  make?: string;
  model?: string;
  mileage?: number;
  price?: number;
  vin?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  seller_name?: string;
  seller_phone?: string;
  images?: string[];
  posted_at?: string;
}

export interface Settings {
  apiUrl: string;
  dealerId: string;
  userLabel: string;
}

export const DEFAULTS: Settings = {
  apiUrl: "http://localhost:8000",
  dealerId: "demo-dealer",
  userLabel: "me",
};

export async function getSettings(): Promise<Settings> {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return stored as Settings;
}

export async function saveSettings(update: Partial<Settings>): Promise<void> {
  await chrome.storage.local.set(update);
}

// Message types routed through the service worker.
export type WorkerMessage =
  | { kind: "ingest"; listing: IngestListing }
  | { kind: "ingestBatch"; listings: IngestListing[] }
  | { kind: "lookupByUrl"; url: string }
  | { kind: "claimLead"; listingId: number };

export interface WorkerResponse<T = unknown> {
  ok: boolean;
  data?: T;
  error?: string;
}

export function callWorker<T = unknown>(
  msg: WorkerMessage,
): Promise<WorkerResponse<T>> {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (resp) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      resolve(resp ?? { ok: false, error: "no response" });
    });
  });
}
