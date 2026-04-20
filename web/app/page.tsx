import Link from "next/link";
import { PageHeader } from "@/components/AppShell";
import { BattleTracker } from "@/components/BattleTracker";
import { FsboApiError, formatPrice, formatRelativeDate, listLeads, listListings } from "@/lib/api";

interface KpiProps {
  label: string;
  value: string;
  delta?: string;
  deltaPositive?: boolean;
  hint?: string;
}

function Kpi({ label, value, delta, deltaPositive, hint }: KpiProps) {
  return (
    <div className="panel p-5">
      <p className="label">{label}</p>
      <div className="mt-2 flex items-baseline gap-2">
        <p className="kpi-value">{value}</p>
        {delta && (
          <span
            className={`text-xs font-medium ${
              deltaPositive ? "text-emerald-600" : "text-rose-600"
            }`}
          >
            {delta}
          </span>
        )}
      </div>
      {hint && <p className="mt-1 text-xs text-ink-500">{hint}</p>}
    </div>
  );
}

async function loadData() {
  try {
    const [priv, all, dealers, scams, leads, recent] = await Promise.all([
      listListings({ classification: "private_seller", limit: 1 }),
      listListings({ classification: "", limit: 1 }),
      listListings({ classification: "dealer", limit: 1 }),
      listListings({ classification: "scam", limit: 1 }),
      listLeads({ limit: 100 }),
      listListings({ classification: "private_seller", limit: 6 }),
    ]);
    return {
      priv: priv.total,
      all: all.total,
      dealers: dealers.total,
      scams: scams.total,
      leads,
      recent: recent.items,
      error: null as string | null,
    };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "API unreachable";
    return { priv: 0, all: 0, dealers: 0, scams: 0, leads: [], recent: [], error: msg };
  }
}

const LEAD_STATUS_STYLES: Record<string, string> = {
  new: "bg-ink-100 text-ink-700",
  contacted: "bg-sky-100 text-sky-800",
  negotiating: "bg-indigo-100 text-indigo-800",
  appointment: "bg-violet-100 text-violet-800",
  purchased: "bg-emerald-100 text-emerald-800",
  lost: "bg-rose-100 text-rose-800",
};

export default async function Home() {
  const data = await loadData();

  const activeLeads = data.leads.filter(
    (l) => l.status !== "purchased" && l.status !== "lost",
  ).length;
  const closed = data.leads.filter((l) => l.status === "purchased").length;
  const filtered = data.dealers + data.scams;
  const signalRate =
    data.all > 0 ? Math.round((data.priv / data.all) * 100) : 0;

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="Pipeline, inventory quality, and recent private-party listings."
        actions={
          <>
            <Link href="/listings" className="btn-secondary">
              Browse listings
            </Link>
            <Link href="/leads" className="btn-primary">
              Open leads ({activeLeads})
            </Link>
          </>
        }
      />

      {data.error && (
        <div className="panel mb-6 border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <strong>Can&apos;t reach the FSBO API.</strong> Set{" "}
          <code className="rounded bg-white px-1">FSBO_API_URL</code> and make sure{" "}
          <code className="rounded bg-white px-1">fsbo-data-platform</code> is running.
          ({data.error})
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Kpi
          label="Private sellers"
          value={data.priv.toLocaleString()}
          hint="Available in feed"
        />
        <Kpi
          label="Active leads"
          value={activeLeads.toLocaleString()}
          hint={`${closed} closed`}
        />
        <Kpi
          label="Signal rate"
          value={`${signalRate}%`}
          hint={`${filtered.toLocaleString()} ads filtered out`}
        />
        <Kpi
          label="Dealers removed"
          value={data.dealers.toLocaleString()}
          hint="Auto-classified"
        />
      </div>

      <div className="mb-4">
        <BattleTracker />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="panel lg:col-span-2">
          <div className="panel-header flex items-center justify-between">
            <h2 className="text-sm font-semibold">Recent private-party listings</h2>
            <Link
              href="/listings"
              className="text-xs font-medium text-brand-600 hover:text-brand-700"
            >
              View all →
            </Link>
          </div>
          {data.recent.length === 0 ? (
            <p className="p-5 text-sm text-ink-500">No listings yet. Run a poll to seed data.</p>
          ) : (
            <ul className="divide-y divide-ink-200">
              {data.recent.map((l) => {
                const vehicle = [l.year, l.make, l.model].filter(Boolean).join(" ") || l.title;
                const loc =
                  [l.city, l.state].filter(Boolean).join(", ") || l.zip_code || "—";
                return (
                  <li key={l.id}>
                    <Link
                      href={`/listings/${l.id}`}
                      className="flex items-center gap-4 px-5 py-3 hover:bg-ink-50"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{vehicle}</p>
                        <p className="truncate text-xs text-ink-500">
                          {loc} · {l.source} ·{" "}
                          {formatRelativeDate(l.posted_at ?? l.first_seen_at)}
                        </p>
                      </div>
                      <p className="text-sm font-semibold tabular">{formatPrice(l.price)}</p>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2 className="text-sm font-semibold">Pipeline</h2>
          </div>
          {data.leads.length === 0 ? (
            <p className="p-5 text-sm text-ink-500">
              No leads yet. Claim a listing to start tracking your outreach.
            </p>
          ) : (
            <ul className="divide-y divide-ink-200">
              {pipelineBuckets(data.leads).map((b) => (
                <li key={b.status} className="flex items-center justify-between px-5 py-3">
                  <span
                    className={`badge ${LEAD_STATUS_STYLES[b.status] ?? "bg-ink-100 text-ink-700"}`}
                  >
                    {b.status.replace("_", " ")}
                  </span>
                  <span className="text-sm font-semibold tabular">{b.count}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}

function pipelineBuckets(leads: Awaited<ReturnType<typeof listLeads>>) {
  const order = ["new", "contacted", "negotiating", "appointment", "purchased", "lost"] as const;
  const counts: Record<string, number> = {};
  for (const l of leads) counts[l.status] = (counts[l.status] ?? 0) + 1;
  return order.map((status) => ({ status, count: counts[status] ?? 0 }));
}
