// Research-backed lead-quality thresholds:
//   >= 80  Hot     — call within 2 hours
//   65-79  Warm    — call within 24h
//   45-64  Monitor — watch for price drops
//   25-44  Cold    — filter out by default
//   < 25   Reject  — hard-hidden unless show_hidden=true

export type Verdict = "hot" | "warm" | "monitor" | "cold" | "reject" | "unknown";

export function verdictForScore(score: number | null | undefined): Verdict {
  if (score === null || score === undefined) return "unknown";
  if (score >= 80) return "hot";
  if (score >= 65) return "warm";
  if (score >= 45) return "monitor";
  if (score >= 25) return "cold";
  return "reject";
}

const VERDICT_STYLE: Record<Verdict, string> = {
  hot: "bg-emerald-100 text-emerald-800 border-emerald-200",
  warm: "bg-sky-100 text-sky-800 border-sky-200",
  monitor: "bg-amber-100 text-amber-800 border-amber-200",
  cold: "bg-rose-100 text-rose-800 border-rose-200",
  reject: "bg-ink-200 text-ink-600 border-ink-300",
  unknown: "bg-ink-100 text-ink-500 border-ink-200",
};

export function ScoreBadge({
  score,
  size = "md",
}: {
  score: number | null | undefined;
  size?: "sm" | "md" | "lg";
}) {
  if (score === null || score === undefined) {
    return <span className="text-ink-400 text-xs tabular">—</span>;
  }
  const verdict = verdictForScore(score);
  const sizing =
    size === "sm"
      ? "px-1.5 py-0 text-[10px]"
      : size === "lg"
        ? "px-3 py-1 text-sm"
        : "px-2 py-0.5 text-xs";
  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold tabular ${VERDICT_STYLE[verdict]} ${sizing}`}
    >
      {score}
    </span>
  );
}

export function ScoreBreakdown({
  breakdown,
}: {
  breakdown: Record<string, number> | undefined;
}) {
  if (!breakdown) return null;
  const entries = Object.entries(breakdown).filter(([k]) => k !== "base");
  if (entries.length === 0) return null;
  // Sort by magnitude (biggest contributors first).
  entries.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  return (
    <div className="mt-3 space-y-1">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-center justify-between text-xs">
          <span className="text-ink-600">{LABELS[key] ?? key.replaceAll("_", " ")}</span>
          <span
            className={`tabular font-medium ${
              value > 0 ? "text-emerald-600" : value < 0 ? "text-rose-600" : "text-ink-500"
            }`}
          >
            {value > 0 ? "+" : ""}
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}

const LABELS: Record<string, string> = {
  price_vs_market: "Price vs market",
  age_sweet_spot: "Age sweet spot",
  mileage_vs_age: "Mileage vs age",
  vin_valid: "VIN valid",
  vin_invalid_checksum: "VIN checksum fails",
  vin_vpic_mismatch: "VIN/decode mismatch",
  image_count: "Image count",
  days_on_market: "Days on market",
  price_drops: "Price drops",
  relist_detected: "Relisted",
  end_of_month: "End of month",
  dealer_risk: "Dealer risk",
  scam_risk: "Scam risk",
  phone_cross_listing: "Phone on other listings",
  phone_provided: "Phone provided",
  title_brand_hard: "Title brand (junk/theft)",
  title_brand_branded: "Title brand (salvage/rebuilt)",
  title_brand_clean: "Title brand (clean)",
  title_text_risk: "Title keyword (risk)",
  title_text_clean: "Title keyword (clean)",
  one_owner: "One owner",
  service_records: "Service records",
  accident_free: "Accident-free",
  negotiable: "Negotiable",
  life_event: "Life-event motivation",
  registration_expiring: "Reg expiring soon",
};
