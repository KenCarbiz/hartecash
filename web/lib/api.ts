// Typed client for the fsbo-data-platform API.
// Keep this file in sync with src/fsbo/api/schemas.py.

export type Classification =
  | "unclassified"
  | "private_seller"
  | "dealer"
  | "scam"
  | "uncertain";

export interface Listing {
  id: number;
  source: string;
  external_id: string;
  url: string;
  title: string | null;
  description: string | null;
  year: number | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  mileage: number | null;
  price: number | null;
  vin: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  seller_phone: string | null;
  classification: Classification;
  classification_confidence: number | null;
  classification_reason: string | null;
  images: string[];
  posted_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
}

export interface ListingsPage {
  items: Listing[];
  total: number;
  limit: number;
  offset: number;
}

export interface ListingsQuery {
  source?: string;
  make?: string;
  model?: string;
  year_min?: number;
  year_max?: number;
  price_min?: number;
  price_max?: number;
  mileage_max?: number;
  zip?: string;
  classification?: Classification | "";
  limit?: number;
  offset?: number;
}

const BASE_URL = process.env.FSBO_API_URL ?? "http://localhost:8000";

function buildUrl(path: string, query?: Record<string, unknown>): string {
  const url = new URL(path, BASE_URL);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export class FsboApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: string,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    next: { revalidate: 30 },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new FsboApiError(`FSBO API ${res.status}`, res.status, body);
  }
  return (await res.json()) as T;
}

export async function listListings(query: ListingsQuery = {}): Promise<ListingsPage> {
  return request<ListingsPage>(buildUrl("/listings", query as Record<string, unknown>));
}

export async function getListing(id: number): Promise<Listing | null> {
  try {
    return await request<Listing>(buildUrl(`/listings/${id}`));
  } catch (err) {
    if (err instanceof FsboApiError && err.status === 404) return null;
    throw err;
  }
}

export function formatPrice(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatMileage(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return `${new Intl.NumberFormat("en-US").format(value)} mi`;
}

export function formatRelativeDate(value: string | null): string {
  if (!value) return "—";
  const then = new Date(value);
  const diffMs = Date.now() - then.getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return then.toLocaleDateString();
}
