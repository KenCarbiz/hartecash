import type { MarketEstimate } from "@/lib/api";
import { formatPrice } from "@/lib/api";

const VERDICT_STYLES: Record<MarketEstimate["verdict"], string> = {
  below: "bg-emerald-100 text-emerald-800 border-emerald-200",
  at: "bg-ink-100 text-ink-700 border-ink-200",
  above: "bg-rose-100 text-rose-800 border-rose-200",
  unknown: "bg-ink-100 text-ink-500 border-ink-200",
};

const VERDICT_LABEL: Record<MarketEstimate["verdict"], string> = {
  below: "Below market",
  at: "At market",
  above: "Above market",
  unknown: "No comps",
};

export function MarketBadge({ estimate }: { estimate: MarketEstimate | null }) {
  if (!estimate || estimate.verdict === "unknown") {
    return (
      <div className="panel p-4">
        <p className="label">Market value</p>
        <p className="mt-1 text-sm text-ink-500">
          Not enough comparable private-party listings yet.
        </p>
      </div>
    );
  }

  const pct = estimate.delta_pct;
  const deltaStr =
    pct !== null
      ? `${pct > 0 ? "+" : ""}${Math.round(pct)}%`
      : "—";

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <p className="label">Market value</p>
        <span
          className={`badge border ${VERDICT_STYLES[estimate.verdict]}`}
        >
          {VERDICT_LABEL[estimate.verdict]}
        </span>
      </div>

      <div className="mt-2 flex items-baseline gap-2">
        <p className="text-lg font-semibold tabular">{formatPrice(estimate.median)}</p>
        <p
          className={`text-sm font-medium tabular ${
            estimate.verdict === "below"
              ? "text-emerald-600"
              : estimate.verdict === "above"
                ? "text-rose-600"
                : "text-ink-500"
          }`}
        >
          asking {deltaStr}
        </p>
      </div>

      <div className="mt-2 text-xs text-ink-500 tabular">
        Range {formatPrice(estimate.p25)} – {formatPrice(estimate.p75)} ·{" "}
        {estimate.sample_size} comp{estimate.sample_size === 1 ? "" : "s"}
      </div>
    </div>
  );
}
