import Link from "next/link";

import { formatDuration, formatPrice, getStaleLeads } from "@/lib/api";

export async function StaleLeadsPanel({ slaMinutes = 5 }: { slaMinutes?: number }) {
  let stale;
  try {
    stale = await getStaleLeads(slaMinutes, 8);
  } catch {
    return null;
  }
  if (!stale || stale.length === 0) return null;

  return (
    <div className="panel mb-4 border-amber-200 bg-amber-50">
      <div className="panel-header flex items-center justify-between border-amber-200 bg-amber-50">
        <div>
          <h3 className="text-sm font-semibold text-amber-900">
            Respond now — {stale.length} lead{stale.length === 1 ? "" : "s"} past SLA
          </h3>
          <p className="text-[11px] text-amber-800 mt-0.5">
            Industry data: response under 5 minutes more than doubles
            contact rates.
          </p>
        </div>
        <span className="badge bg-amber-200 text-amber-900">SLA {slaMinutes}m</span>
      </div>
      <ul className="divide-y divide-amber-200">
        {stale.map((l) => {
          const vehicle =
            [l.listing_year, l.listing_make, l.listing_model]
              .filter(Boolean)
              .join(" ") || l.listing_title || `Listing #${l.listing_id}`;
          const loc =
            [l.listing_city, l.listing_state].filter(Boolean).join(", ") ||
            l.listing_zip ||
            "—";
          return (
            <li key={l.id}>
              <Link
                href={`/listings/${l.listing_id}`}
                className="flex items-center gap-4 px-5 py-3 hover:bg-amber-100"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-amber-950">
                    {vehicle}
                  </p>
                  <p className="truncate text-xs text-amber-800">
                    {loc} · {l.assigned_to ?? "unassigned"}
                  </p>
                </div>
                <p className="text-xs text-amber-800 tabular flex-none">
                  {formatPrice(l.listing_price ?? null)}
                </p>
                <p className="text-xs font-semibold text-rose-700 tabular flex-none w-20 text-right">
                  {formatDuration(l.minutes_since_created)} old
                </p>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

