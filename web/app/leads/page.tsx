import Link from "next/link";
import { PageHeader } from "@/components/AppShell";
import {
  type Lead,
  type LeadStatus,
  FsboApiError,
  formatMileage,
  formatPrice,
  formatRelativeDate,
  listLeads,
} from "@/lib/api";

export const dynamic = "force-dynamic";

const STATUS_STYLES: Record<LeadStatus, string> = {
  new: "bg-ink-100 text-ink-700",
  contacted: "bg-sky-100 text-sky-800",
  negotiating: "bg-indigo-100 text-indigo-800",
  appointment: "bg-violet-100 text-violet-800",
  purchased: "bg-emerald-100 text-emerald-800",
  lost: "bg-rose-100 text-rose-800",
};

const STATUS_ORDER: LeadStatus[] = [
  "new",
  "contacted",
  "negotiating",
  "appointment",
  "purchased",
  "lost",
];

export default async function LeadsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const statusParam =
    (Array.isArray(sp.status) ? sp.status[0] : sp.status) || "active";
  const assignedTo =
    (Array.isArray(sp.assigned_to) ? sp.assigned_to[0] : sp.assigned_to) || undefined;

  let leads: Lead[] = [];
  let error: string | null = null;
  try {
    const fetchStatus: LeadStatus | undefined =
      STATUS_ORDER.includes(statusParam as LeadStatus)
        ? (statusParam as LeadStatus)
        : undefined;
    leads = await listLeads({
      status: fetchStatus,
      assigned_to: assignedTo,
      limit: 200,
    });
    if (statusParam === "active") {
      leads = leads.filter((l) => l.status !== "purchased" && l.status !== "lost");
    }
  } catch (err) {
    error = err instanceof FsboApiError ? err.message : "API unreachable";
  }

  const counts = countByStatus(leads);

  return (
    <>
      <PageHeader
        title="Leads"
        subtitle={`${leads.length} in view${
          assignedTo ? ` · assigned to ${assignedTo}` : ""
        }`}
        actions={
          <Link href="/listings" className="btn-primary">
            Find more listings
          </Link>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        <StatusChip current={statusParam} value="active" label="Active" />
        {STATUS_ORDER.map((s) => (
          <StatusChip
            key={s}
            current={statusParam}
            value={s}
            label={s.replace("_", " ")}
            count={counts[s]}
          />
        ))}
      </div>

      {error && (
        <div className="panel border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Can&apos;t reach the FSBO API. ({error})
        </div>
      )}

      {!error && leads.length === 0 ? (
        <div className="panel p-12 text-center text-sm text-ink-500">
          No leads in this view. Head to{" "}
          <Link href="/listings" className="text-brand-600 hover:text-brand-700">
            Listings
          </Link>{" "}
          and claim one.
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="text-left font-medium px-4 py-2.5">Vehicle</th>
                <th className="text-left font-medium px-4 py-2.5">Location</th>
                <th className="text-right font-medium px-4 py-2.5">Mileage</th>
                <th className="text-right font-medium px-4 py-2.5">Price</th>
                <th className="text-left font-medium px-4 py-2.5">Assigned</th>
                <th className="text-left font-medium px-4 py-2.5">Status</th>
                <th className="text-right font-medium px-4 py-2.5">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {leads.map((l) => {
                const vehicle =
                  [l.listing_year, l.listing_make, l.listing_model]
                    .filter(Boolean)
                    .join(" ") || l.listing_title || "—";
                const loc =
                  [l.listing_city, l.listing_state].filter(Boolean).join(", ") ||
                  l.listing_zip ||
                  "—";
                return (
                  <tr key={l.id} className="hover:bg-ink-50">
                    <td className="px-4 py-3">
                      <Link
                        href={`/listings/${l.listing_id}`}
                        className="block font-medium text-ink-900 hover:text-brand-600"
                      >
                        {vehicle}
                      </Link>
                      <p className="mt-0.5 text-xs text-ink-500">
                        {l.listing_source ?? "—"}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-ink-700">{loc}</td>
                    <td className="px-4 py-3 text-right tabular text-ink-700">
                      {formatMileage(l.listing_mileage ?? null)}
                    </td>
                    <td className="px-4 py-3 text-right tabular font-semibold">
                      {formatPrice(l.listing_price ?? null)}
                    </td>
                    <td className="px-4 py-3 text-ink-700">
                      {l.assigned_to ?? (
                        <span className="text-ink-400">Unassigned</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`badge ${STATUS_STYLES[l.status]}`}>
                        {l.status.replace("_", " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-xs text-ink-500 tabular">
                      {formatRelativeDate(l.updated_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function countByStatus(leads: Lead[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const l of leads) out[l.status] = (out[l.status] ?? 0) + 1;
  return out;
}

function StatusChip({
  current,
  value,
  label,
  count,
}: {
  current: string;
  value: string;
  label: string;
  count?: number;
}) {
  const active = current === value;
  return (
    <Link
      href={value === "active" ? "/leads" : `/leads?status=${value}`}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
        active
          ? "bg-ink-900 text-white"
          : "border border-ink-200 bg-white text-ink-700 hover:bg-ink-50"
      }`}
    >
      {label}
      {count !== undefined && (
        <span
          className={`tabular ${active ? "text-ink-300" : "text-ink-500"}`}
        >
          {count}
        </span>
      )}
    </Link>
  );
}
