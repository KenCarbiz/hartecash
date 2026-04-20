import Link from "next/link";
import { PageHeader } from "@/components/AppShell";
import { FilterBar } from "@/components/FilterBar";
import { ListingsTable } from "@/components/ListingsTable";
import { SavedSearches } from "@/components/SavedSearches";
import {
  type Classification,
  type ListingsQuery,
  FsboApiError,
  listListings,
  listSavedSearches,
} from "@/lib/api";

export const dynamic = "force-dynamic";

function parseQuery(searchParams: Record<string, string | string[] | undefined>): ListingsQuery {
  const s = (k: string) => {
    const v = searchParams[k];
    return Array.isArray(v) ? v[0] : v;
  };
  const n = (k: string) => {
    const v = s(k);
    if (!v) return undefined;
    const parsed = Number(v);
    return Number.isFinite(parsed) ? parsed : undefined;
  };
  const cls = s("classification");
  const sortRaw = s("sort");
  const sort: "posted_at" | "score" | "price" =
    sortRaw === "score" || sortRaw === "price" ? sortRaw : "posted_at";
  return {
    q: s("q") || undefined,
    make: s("make") || undefined,
    model: s("model") || undefined,
    year_min: n("year_min"),
    year_max: n("year_max"),
    price_min: n("price_min"),
    price_max: n("price_max"),
    mileage_max: n("mileage_max"),
    zip: s("zip") || undefined,
    classification: cls === undefined ? "private_seller" : (cls as Classification | ""),
    min_score: n("min_score"),
    sort,
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

  const saved = await listSavedSearches().catch(() => []);

  const limit = query.limit ?? 50;
  const offset = query.offset ?? 0;
  const nextOffset = offset + limit;
  const prevOffset = Math.max(0, offset - limit);
  const qs = (newOffset: number) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      params.set(k, String(v));
    }
    params.set("offset", String(newOffset));
    return `?${params.toString()}`;
  };

  return (
    <>
      <PageHeader
        title="Listings"
        subtitle={`${page.total.toLocaleString()} results · showing ${
          page.items.length === 0 ? 0 : offset + 1
        }–${Math.min(offset + page.items.length, page.total)}`}
      />

      <SavedSearches saved={saved} currentQuery={query} />
      <FilterBar current={query} />

      {error && (
        <div className="panel mt-4 border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Can&apos;t reach the FSBO API. ({error})
        </div>
      )}

      {!error && page.items.length === 0 ? (
        <div className="panel mt-4 p-12 text-center text-sm text-ink-500">
          No listings match your filters. Try widening the criteria.
        </div>
      ) : (
        <div className="mt-4">
          <ListingsTable listings={page.items} />
        </div>
      )}

      {page.items.length > 0 && (
        <div className="mt-4 flex items-center justify-between">
          <Link
            href={qs(prevOffset)}
            aria-disabled={offset === 0}
            className={`btn-secondary ${
              offset === 0 ? "pointer-events-none opacity-40" : ""
            }`}
          >
            ← Previous
          </Link>
          <span className="text-xs text-ink-500 tabular">
            Page {Math.floor(offset / limit) + 1} of{" "}
            {Math.max(1, Math.ceil(page.total / limit))}
          </span>
          <Link
            href={qs(nextOffset)}
            aria-disabled={nextOffset >= page.total}
            className={`btn-secondary ${
              nextOffset >= page.total ? "pointer-events-none opacity-40" : ""
            }`}
          >
            Next →
          </Link>
        </div>
      )}
    </>
  );
}
