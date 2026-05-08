import { getSlaStats } from "@/lib/api";

export async function SlaStatsPanel({ days = 30 }: { days?: number }) {
  let stats;
  try {
    stats = await getSlaStats(days);
  } catch {
    return null;
  }
  if (!stats || stats.leads_total === 0) return null;

  return (
    <div className="panel mb-4">
      <div className="panel-header flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Response SLA</h3>
          <p className="text-[11px] text-ink-500 mt-0.5">
            First-touch time across {stats.leads_total} lead
            {stats.leads_total === 1 ? "" : "s"} in the last {days} days
          </p>
        </div>
        {stats.leads_breached > 0 && (
          <span className="badge bg-rose-100 text-rose-800">
            {stats.leads_breached} breach{stats.leads_breached === 1 ? "" : "es"}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-5">
        <Stat
          label="Median"
          value={formatMin(stats.median_response_minutes)}
          tone={tone(stats.median_response_minutes, 5, 60)}
        />
        <Stat
          label="p90"
          value={formatMin(stats.p90_response_minutes)}
          tone={tone(stats.p90_response_minutes, 30, 120)}
          hint="90% answered within"
        />
        <Stat
          label="Under 5 min"
          value={`${stats.pct_under_5_min}%`}
          tone={
            stats.pct_under_5_min >= 50
              ? "text-emerald-700"
              : stats.pct_under_5_min >= 25
                ? "text-amber-700"
                : "text-rose-700"
          }
          hint="Industry SLA"
        />
        <Stat
          label="Within SLA"
          value={`${stats.leads_within_sla} / ${stats.leads_total}`}
          hint={`SLA = ${stats.sla_minutes} min`}
        />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone?: string;
  hint?: string;
}) {
  return (
    <div>
      <p className="label">{label}</p>
      <p className={`mt-1 text-xl font-semibold tabular ${tone ?? ""}`}>
        {value}
      </p>
      {hint && <p className="mt-0.5 text-[10px] text-ink-500">{hint}</p>}
    </div>
  );
}

function formatMin(m: number | null): string {
  if (m === null) return "—";
  if (m < 60) return `${m}m`;
  const h = m / 60;
  if (h < 24) return `${h.toFixed(1)}h`;
  const d = h / 24;
  return `${d.toFixed(1)}d`;
}

function tone(
  value: number | null,
  goodAtOrBelow: number,
  badAtOrAbove: number,
): string {
  if (value === null) return "";
  if (value <= goodAtOrBelow) return "text-emerald-700";
  if (value >= badAtOrAbove) return "text-rose-700";
  return "text-amber-700";
}
