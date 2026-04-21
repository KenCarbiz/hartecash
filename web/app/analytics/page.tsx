import Link from "next/link";
import { PageHeader } from "@/components/AppShell";
import { getFunnel } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const { days } = await searchParams;
  const window = Number(days) || 30;
  const funnel = await getFunnel(window).catch(() => null);

  if (!funnel) {
    return (
      <>
        <PageHeader title="Analytics" />
        <div className="panel p-5 text-sm text-ink-500">
          Can&apos;t reach the analytics API.
        </div>
      </>
    );
  }

  const stageByKey = Object.fromEntries(funnel.stages.map((s) => [s.key, s]));
  const top = funnel.stages[0]?.count || 1;

  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle={`Conversion funnel over the last ${window} days`}
        actions={
          <div className="flex gap-1.5">
            {[7, 30, 90].map((d) => (
              <Link
                key={d}
                href={`/analytics?days=${d}`}
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  window === d
                    ? "bg-ink-900 text-white"
                    : "border border-ink-200 bg-white text-ink-700 hover:bg-ink-50"
                }`}
              >
                Last {d}d
              </Link>
            ))}
          </div>
        }
      />

      <div className="panel mb-6">
        <div className="panel-header">
          <h2 className="text-sm font-semibold">Funnel</h2>
        </div>
        <div className="p-5 space-y-3">
          {funnel.stages.map((stage, idx) => {
            const prev = idx > 0 ? funnel.stages[idx - 1] : null;
            const convFromPrev =
              prev && prev.count > 0
                ? Math.round((stage.count / prev.count) * 100)
                : null;
            const pctBar = top > 0 ? (stage.count / top) * 100 : 0;
            return (
              <div key={stage.key}>
                <div className="flex items-baseline justify-between text-sm">
                  <span className="font-medium">{stage.label}</span>
                  <div className="flex items-baseline gap-3 tabular">
                    <span className="text-lg font-semibold">
                      {stage.count.toLocaleString()}
                    </span>
                    {convFromPrev !== null && (
                      <span className="text-xs text-ink-500">
                        {convFromPrev}% vs prior
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-1 h-2 w-full rounded-full bg-ink-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-brand-500 transition-all"
                    style={{ width: `${Math.max(pctBar, 2)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        <div className="border-t border-ink-200 p-5 grid grid-cols-3 gap-3 text-center">
          <Stat
            label="Overall conversion"
            value={
              stageByKey.listings_surfaced?.count
                ? `${(
                    ((stageByKey.leads_purchased?.count ?? 0) /
                      stageByKey.listings_surfaced.count) *
                    100
                  ).toFixed(2)}%`
                : "—"
            }
          />
          <Stat
            label="Claim → contact"
            value={
              stageByKey.leads_claimed?.count
                ? `${Math.round(
                    ((stageByKey.leads_contacted?.count ?? 0) /
                      stageByKey.leads_claimed.count) *
                      100,
                  )}%`
                : "—"
            }
          />
          <Stat
            label="Appointment → buy"
            value={
              stageByKey.leads_appointment?.count
                ? `${Math.round(
                    ((stageByKey.leads_purchased?.count ?? 0) /
                      stageByKey.leads_appointment.count) *
                      100,
                  )}%`
                : "—"
            }
          />
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-semibold">By source</h2>
        </div>
        {funnel.sources.length === 0 ? (
          <p className="p-5 text-sm text-ink-500">
            No listings surfaced in this window yet.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="text-left font-medium px-4 py-2.5">Source</th>
                <th className="text-right font-medium px-4 py-2.5">
                  Listings
                </th>
                <th className="text-right font-medium px-4 py-2.5">Claimed</th>
                <th className="text-right font-medium px-4 py-2.5">
                  Purchased
                </th>
                <th className="text-right font-medium px-4 py-2.5">
                  Claim rate
                </th>
                <th className="text-right font-medium px-4 py-2.5">
                  Conversion
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {funnel.sources.map((s) => {
                const claimRate = s.listings
                  ? Math.round((s.leads_claimed / s.listings) * 100)
                  : 0;
                const conv = s.listings
                  ? ((s.leads_purchased / s.listings) * 100).toFixed(2)
                  : "0.00";
                return (
                  <tr key={s.source} className="hover:bg-ink-50">
                    <td className="px-4 py-2.5">{s.source}</td>
                    <td className="px-4 py-2.5 text-right tabular">
                      {s.listings.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular">
                      {s.leads_claimed}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular text-emerald-700">
                      {s.leads_purchased}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-ink-500 tabular">
                      {claimRate}%
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-ink-500 tabular">
                      {conv}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-lg font-semibold tabular">{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-ink-500 mt-0.5">
        {label}
      </p>
    </div>
  );
}
