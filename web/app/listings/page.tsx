import Link from "next/link";
import { PageHeader } from "@/components/AppShell";
import { FilterBar } from "@/components/FilterBar";
import {
  type Classification,
  type ListingsQuery,
  FsboApiError,
  formatMileage,
  formatPrice,
  formatRelativeDate,
  listListings,
} from "@/lib/api";

export const dynamic = "force-dynamic";

const CLASS_BADGE: Record<string, string> = {
  private_seller: "bg-emerald-100 text-emerald-800",
  dealer: "bg-amber-100 text-amber-800",
  scam: "bg-rose-100 text-rose-800",
  uncertain: "bg-ink-100 text-ink-700",
  unclassified: "bg-ink-100 text-ink-600",
};

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
        <div className="panel mt-4 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="text-left font-medium px-4 py-2.5">Vehicle</th>
                <th className="text-left font-medium px-4 py-2.5">Location</th>
                <th className="text-right font-medium px-4 py-2.5">Mileage</th>
                <th className="text-right font-medium px-4 py-2.5">Price</th>
                <th className="text-left font-medium px-4 py-2.5">Source</th>
                <th className="text-left font-medium px-4 py-2.5">Class</th>
                <th className="text-right font-medium px-4 py-2.5">Posted</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {page.items.map((l) => {
                const vehicle =
                  [l.year, l.make, l.model].filter(Boolean).join(" ") || l.title || "—";
                const loc =
                  [l.city, l.state].filter(Boolean).join(", ") || l.zip_code || "—";
                return (
                  <tr key={l.id} className="hover:bg-ink-50">
                    <td className="px-4 py-3">
                      <Link
                        href={`/listings/${l.id}`}
                        className="block font-medium text-ink-900 hover:text-brand-600"
                      >
                        {vehicle}
                      </Link>
                      {l.title && l.title !== vehicle && (
                        <p className="mt-0.5 truncate text-xs text-ink-500 max-w-md">
                          {l.title}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-ink-700">{loc}</td>
                    <td className="px-4 py-3 text-right tabular text-ink-700">
                      {formatMileage(l.mileage)}
                    </td>
                    <td className="px-4 py-3 text-right tabular font-semibold">
                      {formatPrice(l.price)}
                    </td>
                    <td className="px-4 py-3 text-ink-600">{l.source}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`badge ${
                          CLASS_BADGE[l.classification] ?? CLASS_BADGE.unclassified
                        }`}
                      >
                        {l.classification.replace("_", " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-xs text-ink-500 tabular">
                      {formatRelativeDate(l.posted_at ?? l.first_seen_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
