import Link from "next/link";
import { PageHeader } from "@/components/AppShell";
import { AssigneeDropdown } from "@/components/AssigneeDropdown";
import {
  type Lead,
  type LeadStatus,
  FsboApiError,
  formatMileage,
  formatPrice,
  formatRelativeDate,
  getCurrentUser,
  listLeads,
  listTeammates,
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
  const assignedToRaw =
    (Array.isArray(sp.assigned_to) ? sp.assigned_to[0] : sp.assigned_to) || undefined;
  const mineOnly =
    (Array.isArray(sp.mine) ? sp.mine[0] : sp.mine) === "1";

  const user = await getCurrentUser().catch(() => null);
  const effectiveAssignedTo = mineOnly ? user?.email : assignedToRaw;

  let leads: Lead[] = [];
  let error: string | null = null;
  try {
    const fetchStatus: LeadStatus | undefined =
      STATUS_ORDER.includes(statusParam as LeadStatus)
        ? (statusParam as LeadStatus)
        : undefined;
    leads = await listLeads({
      status: fetchStatus,
      assigned_to: effectiveAssignedTo,
      limit: 200,
    });
    if (statusParam === "active") {
      leads = leads.filter((l) => l.status !== "purchased" && l.status !== "lost");
    }
  } catch (err) {
    error = err instanceof FsboApiError ? err.message : "API unreachable";
  }

  const teammates = await listTeammates().catch(() => []);
  const counts = countByStatus(leads);

  // Build CSV export link that preserves current filters.
  const exportParams = new URLSearchParams();
  if (STATUS_ORDER.includes(statusParam as LeadStatus)) {
    exportParams.set("status", statusParam);
  }
  if (effectiveAssignedTo) exportParams.set("assigned_to", effectiveAssignedTo);
  // Route through the Next.js API handler so the session cookie gets
  // forwarded to the backend (works across different prod subdomains).
  const exportHref = `/api/leads/export${
    exportParams.toString() ? `?${exportParams.toString()}` : ""
  }`;

  return (
    <>
      <PageHeader
        title="Leads"
        subtitle={`${leads.length} in view${
          effectiveAssignedTo ? ` · ${effectiveAssignedTo}` : ""
        }`}
        actions={
          <>
            <a
              href={exportHref}
              className="btn-secondary"
              download
            >
              Export CSV
            </a>
            <Link href="/listings" className="btn-primary">
              Find more listings
            </Link>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        <StatusChip current={statusParam} value="active" label="Active" extraQuery={mineOnly ? "&mine=1" : ""} />
        {STATUS_ORDER.map((s) => (
          <StatusChip
            key={s}
            current={statusParam}
            value={s}
            label={s.replace("_", " ")}
            count={counts[s]}
            extraQuery={mineOnly ? "&mine=1" : ""}
          />
        ))}

        {user && (
          <Link
            href={
              mineOnly
                ? `/leads${statusParam && statusParam !== "active" ? `?status=${statusParam}` : ""}`
                : `/leads?mine=1${
                    statusParam && statusParam !== "active" ? `&status=${statusParam}` : ""
                  }`
            }
            className={`ml-2 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
              mineOnly
                ? "bg-brand-600 text-white"
                : "border border-ink-200 bg-white text-ink-700 hover:bg-ink-50"
            }`}
            title="Only leads assigned to me"
          >
            My leads
          </Link>
        )}
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
                    <td className="px-4 py-3">
                      <AssigneeDropdown
                        leadId={l.id}
                        current={l.assigned_to}
                        teammates={teammates}
                        compact
                      />
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
  extraQuery = "",
}: {
  current: string;
  value: string;
  label: string;
  count?: number;
  extraQuery?: string;
}) {
  const active = current === value;
  const href =
    value === "active"
      ? `/leads${extraQuery.startsWith("&") ? `?${extraQuery.slice(1)}` : ""}`
      : `/leads?status=${value}${extraQuery}`;
  return (
    <Link
      href={href}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
        active
          ? "bg-ink-900 text-white"
          : "border border-ink-200 bg-white text-ink-700 hover:bg-ink-50"
      }`}
    >
      {label}
      {count !== undefined && (
        <span className={`tabular ${active ? "text-ink-300" : "text-ink-500"}`}>
          {count}
        </span>
      )}
    </Link>
  );
}
