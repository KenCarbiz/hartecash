/**
 * Pure parsing helpers for the Facebook Marketplace content script.
 *
 * No DOM access here — just regex and shape-walking. Keeps the logic
 * that tends to break when Facebook changes their HTML in one testable
 * place.
 */

import type { IngestListing } from "../lib/api";

const YEAR_RE = /\b(19[89]\d|20[0-3]\d)\b/;

// e.g. "85k mi", "85,000 miles", "85000 mi", "85K MILES"
const MILEAGE_RE = /\b([\d,]+)\s*(k\s*)?(miles?|mi\b)/i;

// $1,500 or $ 15000
const PRICE_RE = /\$\s?([\d,]+)(?!\d)/;

// Title-Case words only so we don't greedy-match lowercase prose before
// the city ("car in Austin, TX" should not produce "car in Austin").
const CITY_STATE_RE =
  /\b([A-Z][a-z.'-]+(?: [A-Z][a-z.'-]+){0,2}),\s?([A-Z]{2})\b/;

// Listed in <City, ST> phrase used on detail pages
const LISTED_IN_RE = /Listed in ([A-Za-z .'-]+,\s?[A-Z]{2})/;


export function extractYear(text: string | null | undefined): number | undefined {
  if (!text) return undefined;
  const m = text.match(YEAR_RE);
  return m ? Number(m[1]) : undefined;
}

export function extractPrice(text: string | null | undefined): number | undefined {
  if (!text) return undefined;
  const m = text.match(PRICE_RE);
  if (!m) return undefined;
  const n = Number(m[1].replace(/,/g, ""));
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

export function extractMileage(text: string | null | undefined): number | undefined {
  if (!text) return undefined;
  const m = text.match(MILEAGE_RE);
  if (!m) return undefined;
  let n = Number(m[1].replace(/,/g, ""));
  if (!Number.isFinite(n)) return undefined;
  if (m[2]) n *= 1000; // "85k" -> 85000
  // Sanity: real used cars don't cross 500k.
  if (n < 100 || n > 500000) return undefined;
  return Math.round(n);
}

export function extractCityState(
  text: string | null | undefined,
): { city: string; state: string } | undefined {
  if (!text) return undefined;
  // Prefer the explicit "Listed in X, ST" anchor when present.
  const listed = text.match(LISTED_IN_RE);
  if (listed) {
    const [city, state] = listed[1].split(",").map((s) => s.trim());
    if (city && state) return { city, state };
  }
  const m = text.match(CITY_STATE_RE);
  if (!m) return undefined;
  return { city: m[1].trim(), state: m[2].trim() };
}

/** Upgrade a Facebook CDN image URL to a larger variant when possible.
 *
 * FB serves multiple sizes differentiated by filename suffix (`_s`, `_t`,
 * `_n`, `_o`) and by URL query params (width/height). This tries a few
 * safe swaps that typically yield a 1024+ px version.
 */
export function upgradeImageUrl(url: string): string {
  if (!url) return url;
  // Common size-suffix pattern: .../1234567_s.jpg -> .../1234567_n.jpg
  return url
    .replace(/_(s|t|q|a|p|o)\.jpg/, "_n.jpg")
    .replace(/_(s|t|q|a|p|o)\.png/, "_n.png");
}

export function bestImageFromTile(card: HTMLElement): string | undefined {
  // Prefer a non-emoji image hosted on scontent.
  const imgs = Array.from(card.querySelectorAll<HTMLImageElement>("img"));
  for (const img of imgs) {
    const src = img.src;
    if (!src) continue;
    if (src.includes("emoji")) continue;
    if (src.includes("scontent") || src.includes("fbcdn")) {
      return upgradeImageUrl(src);
    }
  }
  return undefined;
}


// -----------------------------------------------------------------------
// GraphQL shape walker
// -----------------------------------------------------------------------

interface MarketplaceListingRecord {
  id?: unknown;
  listing_id?: unknown;
  marketplace_listing_id?: unknown;
  title?: unknown;
  marketplace_listing_title?: unknown;
  custom_title?: unknown;
  listing_price?: unknown;
  price?: unknown;
  formatted_price?: unknown;
  primary_listing_photo?: unknown;
  photos?: unknown;
  listing_photos?: unknown;
  location?: unknown;
  redacted_description?: unknown;
  redacted_description_for_seo?: unknown;
  creation_time?: unknown;
  odometer_data?: unknown;
  [key: string]: unknown;
}

function numericId(rec: MarketplaceListingRecord): string | null {
  const raw =
    rec.id || rec.marketplace_listing_id || rec.listing_id;
  if (raw === undefined || raw === null) return null;
  const str = String(raw);
  // Marketplace listing IDs are 10-18 digit numerics.
  if (!/^\d{8,20}$/.test(str)) return null;
  return str;
}

function priceFromRecord(rec: MarketplaceListingRecord): number | undefined {
  const priceObj = rec.listing_price || rec.price || rec.formatted_price;
  if (!priceObj || typeof priceObj !== "object") return undefined;
  const p = priceObj as {
    amount?: string | number;
    amount_with_offset_in_currency?: string;
    formatted_amount?: string;
    formatted_amount_0?: string;
  };
  const candidates = [
    p.amount,
    p.amount_with_offset_in_currency,
    p.formatted_amount,
    p.formatted_amount_0,
  ];
  for (const raw of candidates) {
    if (raw === undefined || raw === null) continue;
    const n = Number(String(raw).replace(/[^0-9.]/g, ""));
    if (Number.isFinite(n) && n > 0) return n;
  }
  return undefined;
}

function imagesFromRecord(rec: MarketplaceListingRecord): string[] {
  const out: string[] = [];
  const primary = rec.primary_listing_photo as
    | { image?: { uri?: string } }
    | undefined;
  const primaryUri = primary?.image?.uri;
  if (typeof primaryUri === "string") out.push(primaryUri);

  const photoList =
    (rec.listing_photos as Array<{ image?: { uri?: string } }> | undefined) ||
    (rec.photos as Array<{ image?: { uri?: string } }> | undefined);
  if (Array.isArray(photoList)) {
    for (const p of photoList.slice(0, 8)) {
      const uri = p?.image?.uri;
      if (typeof uri === "string") out.push(uri);
    }
  }
  // Dedupe while preserving order.
  return Array.from(new Set(out)).slice(0, 8);
}

function mileageFromRecord(rec: MarketplaceListingRecord): number | undefined {
  const odo = rec.odometer_data as
    | { value?: number | string }
    | number
    | undefined;
  if (typeof odo === "number") return extractMileageNumber(odo);
  if (odo && typeof odo === "object") {
    return extractMileageNumber(odo.value);
  }
  return undefined;
}

function extractMileageNumber(v: unknown): number | undefined {
  if (v === undefined || v === null) return undefined;
  const n = Number(String(v).replace(/[^0-9]/g, ""));
  if (!Number.isFinite(n)) return undefined;
  if (n < 100 || n > 500000) return undefined;
  return Math.round(n);
}

function postedAtFromRecord(rec: MarketplaceListingRecord): string | undefined {
  const raw = rec.creation_time as number | string | undefined;
  if (raw === undefined || raw === null) return undefined;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  // Facebook sends Unix seconds.
  const ms = n > 10_000_000_000 ? n : n * 1000;
  return new Date(ms).toISOString();
}

function titleFromRecord(rec: MarketplaceListingRecord): string {
  return String(
    rec.marketplace_listing_title || rec.title || rec.custom_title || "",
  ).trim();
}


/** Convert a Facebook Marketplace listing JSON record to an ingest payload. */
export function graphRecordToIngest(
  rec: MarketplaceListingRecord,
): IngestListing | null {
  const id = numericId(rec);
  if (!id) return null;
  const title = titleFromRecord(rec);
  const price = priceFromRecord(rec);
  const images = imagesFromRecord(rec);
  const mileage = mileageFromRecord(rec);
  const posted_at = postedAtFromRecord(rec);

  const location = (rec.location as
    | {
        reverse_geocode?: { city?: string; state?: string };
        reverse_geocode_detailed?: { city?: string; state?: string };
      }
    | undefined);
  const geo = location?.reverse_geocode_detailed || location?.reverse_geocode;

  const description = String(
    rec.redacted_description ||
      rec.redacted_description_for_seo ||
      "",
  ).trim();

  return {
    source: "facebook_marketplace",
    external_id: id,
    url: `https://www.facebook.com/marketplace/item/${id}`,
    title,
    description: description || undefined,
    year: extractYear(title),
    price,
    mileage,
    city: geo?.city,
    state: geo?.state,
    images,
    posted_at,
  };
}

/** Recursively walk a parsed GraphQL payload and yield every object that
 *  looks like a marketplace listing record. Exported for tests. */
export function walkForListingRecords(
  obj: unknown,
  depth: number = 0,
  visited: WeakSet<object> = new WeakSet(),
): MarketplaceListingRecord[] {
  const out: MarketplaceListingRecord[] = [];
  if (depth > 12 || obj === null || typeof obj !== "object") return out;
  if (visited.has(obj as object)) return out;
  visited.add(obj as object);

  if (Array.isArray(obj)) {
    for (const item of obj) out.push(...walkForListingRecords(item, depth + 1, visited));
    return out;
  }

  const rec = obj as MarketplaceListingRecord;
  const title = titleFromRecord(rec);
  const id = numericId(rec);
  const priceObj = rec.listing_price || rec.price || rec.formatted_price;
  if (id && title && priceObj) {
    out.push(rec);
  }

  for (const key in rec) {
    out.push(...walkForListingRecords(rec[key], depth + 1, visited));
  }
  return out;
}
