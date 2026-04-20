import Link from "next/link";

import {
  deleteSavedSearchAction,
  saveCurrentSearch,
} from "@/app/listings/save-search-action";
import type { ListingsQuery, SavedSearch } from "@/lib/api";

function querystring(query: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    params.set(k, String(v));
  }
  const str = params.toString();
  return str ? `?${str}` : "";
}

export function SavedSearches({
  saved,
  currentQuery,
}: {
  saved: SavedSearch[];
  currentQuery: ListingsQuery;
}) {
  // Strip the pagination cursor from the saved query.
  const cleanQuery = { ...currentQuery };
  delete cleanQuery.limit;
  delete cleanQuery.offset;

  return (
    <div className="panel mb-4">
      <div className="panel-header flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold">Saved searches</h3>
          <p className="text-[11px] text-ink-500 mt-0.5">
            Save the current filters to re-run with one click.
          </p>
        </div>
        <form action={saveCurrentSearch} className="flex items-center gap-2">
          <input
            type="text"
            name="name"
            placeholder="Name this search"
            required
            className="input w-52"
          />
          <input type="hidden" name="query" value={JSON.stringify(cleanQuery)} />
          <label className="flex items-center gap-1 text-[11px] text-ink-600">
            <input type="checkbox" name="alerts_enabled" className="accent-brand-600" />
            Alerts
          </label>
          <button type="submit" className="btn-secondary">
            Save
          </button>
        </form>
      </div>
      {saved.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 p-3">
          {saved.map((s) => (
            <li key={s.id} className="flex items-center gap-1">
              <Link
                href={`/listings${querystring(s.query)}`}
                className="rounded-full border border-ink-200 bg-white px-3 py-1 text-xs text-ink-700 hover:bg-ink-50"
              >
                {s.name}
                {s.alerts_enabled && <span className="ml-1 text-brand-600">🔔</span>}
              </Link>
              <form action={deleteSavedSearchAction} className="inline">
                <input type="hidden" name="id" value={s.id} />
                <button
                  type="submit"
                  className="text-ink-400 hover:text-rose-600 text-xs"
                  title="Delete"
                  aria-label={`Delete ${s.name}`}
                >
                  ×
                </button>
              </form>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
