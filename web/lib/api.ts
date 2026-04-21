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
  dealer_likelihood?: number | null;
  scam_score?: number | null;
  lead_quality_score?: number | null;
  quality_breakdown?: Record<string, number>;
  auto_hidden?: boolean;
  auto_hide_reason?: string | null;
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
  min_score?: number;
  sort?: "posted_at" | "score" | "price";
  near_zip?: string;
  radius_miles?: number;
  limit?: number;
  offset?: number;
}

const BASE_URL = process.env.FSBO_API_URL ?? "http://localhost:8000";

// Dev-mode header fallback. Production auth comes from the session cookie.
const DEMO_DEALER_ID = process.env.DEMO_DEALER_ID ?? "demo-dealer";

/** On the server, forward the incoming request's session cookie to the
 * backend API so RSC fetches are authenticated. No-op in the browser. */
async function sessionCookie(): Promise<string | undefined> {
  if (typeof window !== "undefined") return undefined;
  try {
    const { cookies } = await import("next/headers");
    const store = await cookies();
    const c = store.get("autocurb_session");
    return c ? `autocurb_session=${c.value}` : undefined;
  } catch {
    return undefined;
  }
}

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

/** Single entrypoint for all backend calls. Forwards:
 *  - Cookie (session) on the server
 *  - X-Dealer-Id dev fallback (stripped in production by the backend)
 *  - Content-Type: application/json for JSON-body requests
 *  - Accept: application/json
 */
async function apiFetch(pathOrUrl: string, init: RequestInit = {}): Promise<Response> {
  const url = pathOrUrl.startsWith("http") ? pathOrUrl : buildUrl(pathOrUrl);
  const cookie = await sessionCookie();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body !== undefined && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (cookie) headers["Cookie"] = cookie;
  // Dev-mode fallback. Backend resolver only honors it when ENV_MODE != "production".
  if (!cookie) headers["X-Dealer-Id"] = DEMO_DEALER_ID;
  Object.assign(headers, (init.headers as Record<string, string>) ?? {});
  return fetch(url, { ...init, headers, cache: init.cache ?? "no-store" });
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const path = url.replace(BASE_URL, "");
  const res = await apiFetch(path, init);
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

// ---------- auth ----------

export interface CurrentUser {
  id: number;
  email: string;
  name: string | null;
  dealer_id: string;
  role: string;
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  const res = await apiFetch("/auth/me");
  if (res.status === 401) return null;
  if (!res.ok) return null;
  return (await res.json()) as CurrentUser;
}

// ---------- notification preferences ----------

export interface NotificationPreferences {
  alerts_enabled: boolean;
  alert_min_score: number;
}

export async function getNotificationPrefs(): Promise<NotificationPreferences | null> {
  const res = await apiFetch("/notifications/preferences");
  if (!res.ok) return null;
  return (await res.json()) as NotificationPreferences;
}

export async function updateNotificationPrefs(
  patch: Partial<NotificationPreferences>,
): Promise<NotificationPreferences> {
  const res = await apiFetch("/notifications/preferences", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  if (!res.ok)
    throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as NotificationPreferences;
}

// ---------- source health ----------

export interface SourceHealth {
  source: string;
  total_listings: number;
  listings_last_24h: number;
  listings_last_7d: number;
  last_scrape_at: string | null;
  last_scrape_error: string | null;
  recent_inserted: number;
  recent_updated: number;
}

export interface ScrapeRunRow {
  id: number;
  source: string;
  params: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
  fetched_count: number;
  inserted_count: number;
  updated_count: number;
  error: string | null;
}

export async function getSourceHealth(): Promise<SourceHealth[]> {
  const res = await apiFetch(buildUrl("/sources/health"), { cache: "no-store" });
  if (!res.ok) return [];
  return (await res.json()) as SourceHealth[];
}

export async function getScrapeRuns(source?: string): Promise<ScrapeRunRow[]> {
  const res = await apiFetch(
    buildUrl("/sources/runs", source ? { source, limit: 50 } : { limit: 50 }),
  );
  if (!res.ok) return [];
  return (await res.json()) as ScrapeRunRow[];
}

// ---------- API keys ----------

export interface ApiKeyRow {
  id: number;
  dealer_id: string;
  name: string;
  token_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreated extends ApiKeyRow {
  token: string;
}

export async function listApiKeys(): Promise<ApiKeyRow[]> {
  const res = await apiFetch(buildUrl("/api-keys"), {
    headers: crmHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as ApiKeyRow[];
}

export async function createApiKey(name: string): Promise<ApiKeyCreated> {
  const res = await apiFetch(buildUrl("/api-keys"), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as ApiKeyCreated;
}

// ---------- invitations ----------

export interface InvitationRow {
  id: number;
  dealer_id: string;
  email: string;
  role: string;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
}

export interface InvitationCreated extends InvitationRow {
  token: string;
  accept_url_hint: string;
}

export async function listInvitations(): Promise<InvitationRow[]> {
  const res = await apiFetch("/invitations");
  if (!res.ok)
    throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as InvitationRow[];
}

export async function createInvitation(
  email: string,
  role: string = "member",
): Promise<InvitationCreated> {
  const res = await apiFetch("/invitations", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new FsboApiError(`FSBO API ${res.status}`, res.status, body);
  }
  return (await res.json()) as InvitationCreated;
}

export async function revokeInvitation(id: number): Promise<InvitationRow> {
  const res = await apiFetch(`/invitations/${id}/revoke`, { method: "POST" });
  if (!res.ok)
    throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as InvitationRow;
}

export interface InvitationPreview {
  email: string;
  role: string;
  dealer_id: string;
  dealer_name: string | null;
  invited_by_email: string | null;
  expires_at: string;
}

export async function previewInvitation(
  token: string,
): Promise<InvitationPreview | { error: string }> {
  const res = await apiFetch(`/invitations/preview?token=${encodeURIComponent(token)}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return { error: body.detail || `error ${res.status}` };
  }
  return (await res.json()) as InvitationPreview;
}

export async function revokeApiKey(id: number): Promise<ApiKeyRow> {
  const res = await apiFetch(buildUrl(`/api-keys/${id}/revoke`), {
    method: "POST",
    headers: crmHeaders(),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as ApiKeyRow;
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
// crmHeaders retained for backwards compatibility with a few call sites
// that still inline their own fetch. Prefer apiFetch() which auto-applies
// cookie + dev-fallback + content-type.
function crmHeaders(dealerId: string = DEMO_DEALER_ID): HeadersInit {
  return { "X-Dealer-Id": dealerId, "Content-Type": "application/json" };
}

export interface Teammate {
  email: string;
  name: string | null;
  role: string;
}

export async function listTeammates(): Promise<Teammate[]> {
  const res = await apiFetch("/leads/teammates");
  if (!res.ok) return [];
  return (await res.json()) as Teammate[];
}

export async function listLeads(params: {
  status?: LeadStatus;
  assigned_to?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<Lead[]> {
  const res = await apiFetch(buildUrl("/leads", params as Record<string, unknown>), {
    headers: crmHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as Lead[];
}

export async function getLeadForListing(listingId: number): Promise<Lead | null> {
  const res = await apiFetch(buildUrl(`/leads/by-listing/${listingId}`), {
    headers: crmHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  const body = await res.text();
  if (!body || body === "null") return null;
  return JSON.parse(body) as Lead;
}

export async function createLead(listingId: number, assignedTo?: string): Promise<Lead> {
  const res = await apiFetch(buildUrl("/leads"), {
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
  const res = await apiFetch(buildUrl(`/leads/${leadId}`), {
    method: "PATCH",
    headers: crmHeaders(),
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as Lead;
}

export async function listInteractions(leadId: number): Promise<Interaction[]> {
  const res = await apiFetch(buildUrl(`/leads/${leadId}/interactions`), {
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
  const res = await apiFetch(buildUrl(`/listings/${listingId}/market`), {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as MarketEstimate;
}

export async function bulkClaim(
  listingIds: number[],
  assignedTo?: string,
): Promise<{ claimed: number; already_claimed: number; missing_listings: number[] }> {
  const res = await apiFetch(buildUrl("/leads/bulk-claim"), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify({ listing_ids: listingIds, assigned_to: assignedTo ?? null }),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return await res.json();
}

// ---------- listing stats (days on market, price history) ----------

export interface PriceHistoryPoint {
  price: number;
  delta: number | null;
  observed_at: string;
}

export interface ListingStats {
  listing_id: number;
  days_on_market: number | null;
  price_drops: number;
  total_drop_amount: number | null;
  last_price_change_at: string | null;
  price_history: PriceHistoryPoint[];
}

export async function getListingStats(listingId: number): Promise<ListingStats | null> {
  const res = await apiFetch(buildUrl(`/listings/${listingId}/stats`), {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as ListingStats;
}

// ---------- duplicates ----------

export interface DuplicateRow {
  id: number;
  source: string;
  url: string;
  posted_at: string | null;
  dedup_key: string | null;
}

export interface VehicleFileSource {
  id: number;
  source: string;
  external_id: string;
  url: string;
  price: number | null;
  first_seen_at: string;
  posted_at: string | null;
}

export interface VehicleFilePriceHistoryRow {
  price: number;
  delta: number | null;
  observed_at: string;
  source: string;
}

export interface VehicleFile {
  primary_listing_id: number;
  dedup_key: string | null;
  title: string | null;
  year: number | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  mileage: number | null;
  vin: string | null;
  city: string | null;
  state: string | null;
  min_price: number | null;
  max_price: number | null;
  latest_price: number | null;
  price_drop_pct: number | null;
  oldest_first_seen_at: string | null;
  days_on_market: number | null;
  total_sources: number;
  sources: VehicleFileSource[];
  images: string[];
  price_history: VehicleFilePriceHistoryRow[];
}

export async function getVehicleFile(
  listingId: number,
): Promise<VehicleFile | null> {
  const res = await apiFetch(`/listings/${listingId}/vehicle-file`);
  if (!res.ok) return null;
  return (await res.json()) as VehicleFile;
}

export interface FunnelStage {
  label: string;
  key: string;
  count: number;
}

export interface FunnelSourceRow {
  source: string;
  listings: number;
  leads_claimed: number;
  leads_purchased: number;
}

export interface FunnelResponse {
  dealer_id: string;
  since: string;
  until: string;
  stages: FunnelStage[];
  sources: FunnelSourceRow[];
}

export async function getFunnel(days: number = 30): Promise<FunnelResponse | null> {
  const res = await apiFetch(`/analytics/funnel?days=${days}`);
  if (!res.ok) return null;
  return (await res.json()) as FunnelResponse;
}

export async function listDuplicates(listingId: number): Promise<DuplicateRow[]> {
  const res = await apiFetch(buildUrl(`/listings/${listingId}/duplicates`), {
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
  const res = await apiFetch(buildUrl("/saved-searches"), {
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
  const res = await apiFetch(buildUrl("/saved-searches"), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify({ name, query, alerts_enabled: alertsEnabled }),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as SavedSearch;
}

export async function deleteSavedSearch(id: number): Promise<void> {
  await apiFetch(buildUrl(`/saved-searches/${id}`), {
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

export async function createTemplate(
  name: string,
  category: string,
  body: string,
): Promise<MessageTemplate> {
  const res = await apiFetch("/templates", {
    method: "POST",
    body: JSON.stringify({ name, category, body }),
  });
  if (!res.ok)
    throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as MessageTemplate;
}

export async function updateTemplate(
  id: number,
  patch: Partial<Pick<MessageTemplate, "name" | "category" | "body">>,
): Promise<MessageTemplate> {
  const res = await apiFetch(`/templates/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  if (!res.ok)
    throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as MessageTemplate;
}

export async function deleteTemplate(id: number): Promise<void> {
  const res = await apiFetch(`/templates/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204)
    throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
}

export async function renderTemplate(
  templateId: number,
  listingId: number,
): Promise<{ template_id: number; rendered: string }> {
  const res = await apiFetch(buildUrl(`/templates/${templateId}/render/${listingId}`), {
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
  const res = await apiFetch(buildUrl("/ai/opener"), {
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
  const res = await apiFetch(buildUrl("/activity/summary", { user_id: userId }), {
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
  await apiFetch(buildUrl("/activity/bump"), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify(body),
  });
}

// ---------- messaging ----------

export interface SendSmsResult {
  message_id: number;
  twilio_sid: string | null;
  status: string;
  error: string | null;
}

export async function sendSms(leadId: number, body: string, to?: string): Promise<SendSmsResult> {
  const res = await apiFetch(buildUrl("/messages/send"), {
    method: "POST",
    headers: crmHeaders(),
    body: JSON.stringify({ lead_id: leadId, body, to_number: to ?? null }),
  });
  if (!res.ok) throw new FsboApiError(`FSBO API ${res.status}`, res.status, await res.text());
  return (await res.json()) as SendSmsResult;
}

export async function addInteraction(
  leadId: number,
  kind: InteractionKind,
  body: string,
  direction?: string,
): Promise<Interaction> {
  const res = await apiFetch(buildUrl(`/leads/${leadId}/interactions`), {
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
