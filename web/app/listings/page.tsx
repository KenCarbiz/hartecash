import Link from "next/link";
import { FilterBar } from "@/components/FilterBar";
import { ListingCard } from "@/components/ListingCard";
import {
  type Classification,
  type ListingsQuery,
  FsboApiError,
  listListings,
} from "@/lib/api";

export const dynamic = "force-dynamic";

function parseQuery(searchParams: Record<string, string | string[] | undefined>): ListingsQuery {
  const s = (k: string) => {
    const v = searchParams[k];
    if (Array.isArray(v)) return v[0];
    return v;
  };
  const n = (k: string) => {
    const v = s(k);
    if (!v) return undefined;
    const parsed = Number(v);
    return Number.isFinite(parsed) ? parsed : undefined;
  };
  const cls = s("classification");
  return {
    make: s("make") || undefined,
    model: s("model") || undefined,
    year_min: n("year_min"),
    year_max: n("year_max"),
    price_min: n("price_min"),
    price_max: n("price_max"),
    mileage_max: n("mileage_max"),
    zip: s("zip") || undefined,
    classification:
      cls === undefined ? "private_seller" : (cls as Classification | ""),
    limit: n("limit") ?? 50,
    offset: n("offset") ?? 0,
  };
}

export default async function ListingsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const query = parseQuery(sp);

  let page;
  let error: string | null = null;
  try {
    page = await listListings(query);
  } catch (err) {
    error = err instanceof FsboApiError ? err.message : "API unreachable";
    page = { items: [], total: 0, limit: query.limit ?? 50, offset: query.offset ?? 0 };
  }

  const nextOffset = (query.offset ?? 0) + (query.limit ?? 50);
  const prevOffset = Math.max(0, (query.offset ?? 0) - (query.limit ?? 50));
  const qs = (offset: number) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") continue;
      params.set(key, String(value));
    }
    params.set("offset", String(offset));
    return `?${params.toString()}`;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Listings</h1>
          <p className="mt-1 text-sm text-slate-500">
            {page.total.toLocaleString()} results · showing {page.offset + 1}–
            {Math.min(page.offset + page.items.length, page.total)}
          </p>
        </div>
      </div>

      <FilterBar current={query} />

      {error && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-900/20 p-4 text-sm">
          Can&apos;t reach the FSBO API. ({error})
        </div>
      )}

      {!error && page.items.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 dark:border-slate-700 p-12 text-center text-sm text-slate-500">
          No listings match your filters. Try widening the criteria.
        </div>
      )}

      <div className="space-y-3">
        {page.items.map((listing) => (
          <ListingCard key={listing.id} listing={listing} />
        ))}
      </div>

      {page.items.length > 0 && (
        <div className="flex items-center justify-between">
          <Link
            href={qs(prevOffset)}
            aria-disabled={page.offset === 0}
            className={`rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm ${
              page.offset === 0 ? "pointer-events-none opacity-40" : "hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
          >
            ← Previous
          </Link>
          <Link
            href={qs(nextOffset)}
            aria-disabled={nextOffset >= page.total}
            className={`rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm ${
              nextOffset >= page.total
                ? "pointer-events-none opacity-40"
                : "hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
          >
            Next →
          </Link>
        </div>
      )}
    </div>
  );
}
