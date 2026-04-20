import type { ListingStats } from "@/lib/api";
import { formatPrice, formatRelativeDate } from "@/lib/api";

export function ListingTimeline({ stats }: { stats: ListingStats | null }) {
  if (!stats) return null;

  const { days_on_market, price_drops, total_drop_amount, price_history } = stats;

  return (
    <div className="panel p-4">
      <p className="label">Market signal</p>

      <div className="mt-2 grid grid-cols-3 gap-3 text-center">
        <Stat
          label="Days on market"
          value={days_on_market?.toString() ?? "—"}
          tone={tone(days_on_market)}
        />
        <Stat
          label="Price drops"
          value={price_drops.toString()}
          tone={price_drops > 0 ? "good" : "neutral"}
        />
        <Stat
          label="Total dropped"
          value={total_drop_amount ? `-${formatPrice(total_drop_amount)}` : "—"}
          tone={total_drop_amount ? "good" : "neutral"}
        />
      </div>

      {price_history.length > 1 && (
        <div className="mt-4 pt-3 border-t border-ink-200">
          <p className="label mb-2">Price history</p>
          <ul className="space-y-1.5">
            {price_history.slice().reverse().map((p, idx) => (
              <li
                key={`${p.observed_at}-${idx}`}
                className="flex items-center justify-between text-xs tabular"
              >
                <span className="text-ink-500">{formatRelativeDate(p.observed_at)}</span>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{formatPrice(p.price)}</span>
                  {p.delta !== null && p.delta !== 0 && (
                    <span
                      className={`text-[10px] ${
                        p.delta < 0 ? "text-emerald-600" : "text-rose-600"
                      }`}
                    >
                      {p.delta > 0 ? "+" : ""}
                      {formatPrice(p.delta)}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "good" | "warn" | "bad" | "neutral";
}) {
  const color = {
    good: "text-emerald-600",
    warn: "text-amber-600",
    bad: "text-rose-600",
    neutral: "text-ink-800",
  }[tone];
  return (
    <div>
      <p className={`text-sm font-semibold tabular ${color}`}>{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-ink-500 mt-0.5">
        {label}
      </p>
    </div>
  );
}

function tone(days: number | null): "good" | "warn" | "bad" | "neutral" {
  if (days === null) return "neutral";
  if (days <= 3) return "good";
  if (days <= 30) return "neutral";
  if (days <= 60) return "warn";
  return "bad";
}
