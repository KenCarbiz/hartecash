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
  q?: string;
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

// ---------- CRM ----------

export type LeadStatus =
  | "new"
  | "contacted"
  | "negotiating"
  | "appointment"
  | "purchased"
  | "lost";

export type InteractionKind =
  | "note"
  | "call"
  | "text"
  | "email"
  | "task"
  | "status_change";

export interface Lead {
  id: number;
  dealer_id: string;
  listing_id: number;
  assigned_to: string | null;
  status: LeadStatus;
  offered_price: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  // Present on inbox list endpoint (LeadWithListing); absent on single-lead lookup.
  listing_title?: string | null;
  listing_year?: number | null;
  listing_make?: string | null;
  listing_model?: string | null;
  listing_price?: number | null;
  listing_mileage?: number | null;
  listing_city?: string | null;
  listing_state?: string | null;
  listing_zip?: string | null;
  listing_source?: string;
}

export interface Interaction {
  id: number;
  lead_id: number;
  kind: InteractionKind;
  direction: string | null;
  actor: string | null;
  body: string | null;
  due_at: string | null;
  completed_at: string | null;
  meta: Record<string, unknown>;
  created_at: string;
}

// Demo-only dealer ID. Replace with auth-derived value once auth lands.
const DEMO_DEALER_ID = process.env.DEMO_DEALER_ID ?? "demo-dealer";

function crmHeaders(dealerId: string = DEMO_DEALER_ID): HeadersInit {
  return { "X-Dealer-Id": dealerId, "Content-Type": "application/json" };
}

export async function listLeads(params: {
  status?: LeadStatus;
  assigned_to?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Lead[]> {
  const res = await fetch(buildUrl("/leads", params as Record<string, unknown>), {
    headers: crmHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as Lead[];
}

export async function getLeadForListing(listingId: number): Promise<Lead | null> {
  const res = await fetch(buildUrl(`/leads/by-listing/${listingId}`), {
    headers: crmHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  const body = await res.text();
  if (!body || body === "null") return null;
  return JSON.parse(body) as Lead;
}

export async function createLead(listingId: number, assignedTo?: string): Promise<Lead> {
  const res = await fetch(buildUrl("/leads"), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify({ listing_id: listingId, assigned_to: assignedTo ?? null }),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as Lead;
}

export async function patchLead(
  leadId: number,
  patch: Partial<Pick<Lead, "status" | "assigned_to" | "offered_price" | "notes">>,
): Promise<Lead> {
  const res = await fetch(buildUrl(`/leads/${leadId}`), {
    method: "PATCH",
    headers: crmHeaders(),
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as Lead;
}

export async function listInteractions(leadId: number): Promise<Interaction[]> {
  const res = await fetch(buildUrl(`/leads/${leadId}/interactions`), {
    headers: crmHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as Interaction[];
}

// ---------- valuation ----------

export interface MarketEstimate {
  sample_size: number;
  median: number | null;
  p25: number | null;
  p75: number | null;
  listing_price: number | null;
  delta_pct: number | null;
  verdict: "below" | "at" | "above" | "unknown";
}

export async function getMarketEstimate(listingId: number): Promise<MarketEstimate | null> {
  const res = await fetch(buildUrl(`/listings/${listingId}/market`), {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as MarketEstimate;
}

export async function bulkClaim(
  listingIds: number[],
  assignedTo?: string,
): Promise<{ claimed: number; already_claimed: number; missing_listings: number[] }> {
  const res = await fetch(buildUrl("/leads/bulk-claim"), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify({ listing_ids: listingIds, assigned_to: assignedTo ?? null }),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return await res.json();
}

// ---------- duplicates ----------

export interface DuplicateRow {
  id: number;
  source: string;
  url: string;
  posted_at: string | null;
  dedup_key: string | null;
}

export async function listDuplicates(listingId: number): Promise<DuplicateRow[]> {
  const res = await fetch(buildUrl(`/listings/${listingId}/duplicates`), {
    cache: "no-store",
  });
  if (!res.ok) return [];
  return (await res.json()) as DuplicateRow[];
}

// ---------- saved searches ----------

export interface SavedSearch {
  id: number;
  dealer_id: string;
  name: string;
  query: Record<string, unknown>;
  alerts_enabled: boolean;
  last_run_at: string | null;
  created_at: string;
}

export async function listSavedSearches(): Promise<SavedSearch[]> {
  const res = await fetch(buildUrl("/saved-searches"), {
    headers: crmHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as SavedSearch[];
}

export async function createSavedSearch(
  name: string,
  query: Record<string, unknown>,
  alertsEnabled = false,
): Promise<SavedSearch> {
  const res = await fetch(buildUrl("/saved-searches"), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify({ name, query, alerts_enabled: alertsEnabled }),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as SavedSearch;
}

export async function deleteSavedSearch(id: number): Promise<void> {
  await fetch(buildUrl(`/saved-searches/${id}`), {
    method: "DELETE",
    headers: crmHeaders(),
  });
}

// ---------- templates ----------

export interface MessageTemplate {
  id: number;
  dealer_id: string;
  name: string;
  category: string;
  body: string;
  is_default: boolean;
  created_at: string;
}

export async function listTemplates(category?: string): Promise<MessageTemplate[]> {
  const res = await fetch(
    buildUrl("/templates", category ? { category } : undefined),
    { headers: crmHeaders(), cache: "no-store" },
  );
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as MessageTemplate[];
}

export async function renderTemplate(
  templateId: number,
  listingId: number,
): Promise<{ template_id: number; rendered: string }> {
  const res = await fetch(buildUrl(`/templates/${templateId}/render/${listingId}`), {
    headers: crmHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return await res.json();
}

// ---------- AI ----------

export async function aiOpener(
  listingId: number,
  tone: "direct" | "friendly" | "cash-buyer" = "direct",
): Promise<{ message: string; tone: string; listing_id: number }> {
  const res = await fetch(buildUrl("/ai/opener"), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify({ listing_id: listingId, tone }),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return await res.json();
}

// ---------- activity / battle tracker ----------

export interface BattleSummary {
  today: {
    dealer_id: string;
    user_id: string;
    date: string;
    messages_sent: number;
    calls_made: number;
    offers_made: number;
    appointments: number;
    purchases: number;
    goal_messages: number;
  };
  goal_pct: number;
  streak_days: number;
  week_totals: {
    messages_sent: number;
    calls_made: number;
    offers_made: number;
    appointments: number;
    purchases: number;
  };
}

export async function getBattleSummary(userId = "me"): Promise<BattleSummary> {
  const res = await fetch(buildUrl("/activity/summary", { user_id: userId }), {
    headers: crmHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return await res.json();
}

export async function bumpActivity(body: {
  user_id?: string;
  messages_sent?: number;
  calls_made?: number;
  offers_made?: number;
  appointments?: number;
  purchases?: number;
}): Promise<void> {
  await fetch(buildUrl("/activity/bump"), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify(body),
  });
}

export async function addInteraction(
  leadId: number,
  kind: InteractionKind,
  body: string,
  direction?: string,
): Promise<Interaction> {
  const res = await fetch(buildUrl(`/leads/${leadId}/interactions`), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify({ kind, body, direction: direction ?? null }),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as Interaction;
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
