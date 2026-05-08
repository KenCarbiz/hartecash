import Link from "next/link";

import { formatRelativeDate, getActivityLog, type ActivityRow } from "@/lib/api";

const KIND_STYLES: Record<string, string> = {
  text: "bg-sky-100 text-sky-800",
  email: "bg-violet-100 text-violet-800",
  call: "bg-amber-100 text-amber-800",
  note: "bg-ink-100 text-ink-700",
  status_change: "bg-emerald-100 text-emerald-800",
  task: "bg-indigo-100 text-indigo-800",
};

export async function ActivityLogPanel({ limit = 25 }: { limit?: number }) {
  const log = await getActivityLog({ limit }).catch(() => null);
  if (!log || log.rows.length === 0) return null;

  return (
    <div className="panel mb-6">
      <div className="panel-header flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Recent activity</h3>
          <p className="text-[11px] text-ink-500 mt-0.5">
            Cross-lead audit feed — who did what when
          </p>
        </div>
        {log.has_more && (
          <span className="text-[11px] text-ink-500">
            Showing latest {log.rows.length}
          </span>
        )}
      </div>
      <ul className="divide-y divide-ink-200">
        {log.rows.map((row) => (
          <ActivityRowView key={row.interaction_id} row={row} />
        ))}
      </ul>
    </div>
  );
}

function ActivityRowView({ row }: { row: ActivityRow }) {
  const kindStyle = KIND_STYLES[row.kind] ?? "bg-ink-100 text-ink-700";
  const arrow = row.direction === "outbound" ? "→" : row.direction === "inbound" ? "←" : "";

  return (
    <li className="px-5 py-3 text-sm">
      <div className="flex items-baseline gap-3">
        <span className={`badge ${kindStyle} flex-none`}>
          {row.kind.replace("_", " ")}
          {arrow && <span className="ml-1">{arrow}</span>}
        </span>
        <Link
          href={`/listings/${row.listing_id}`}
          className="truncate font-medium text-ink-900 hover:text-brand-600"
        >
          {row.listing_title || `Listing #${row.listing_id}`}
        </Link>
        <span className="ml-auto flex-none text-[11px] text-ink-500 tabular">
          {formatRelativeDate(row.created_at)}
        </span>
      </div>
      {row.body && (
        <p className="mt-1 text-xs text-ink-600 line-clamp-2">{row.body}</p>
      )}
      {row.actor && (
        <p className="mt-1 text-[11px] text-ink-500">
          by <span className="font-medium text-ink-700">{row.actor}</span>
        </p>
      )}
    </li>
  );
}
