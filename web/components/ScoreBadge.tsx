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
  const color =
    score >= 80
      ? "bg-emerald-100 text-emerald-800 border-emerald-200"
      : score >= 60
        ? "bg-sky-100 text-sky-800 border-sky-200"
        : score >= 40
          ? "bg-amber-100 text-amber-800 border-amber-200"
          : "bg-rose-100 text-rose-800 border-rose-200";
  const sizing =
    size === "sm"
      ? "px-1.5 py-0 text-[10px]"
      : size === "lg"
        ? "px-3 py-1 text-sm"
        : "px-2 py-0.5 text-xs";
  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold tabular ${color} ${sizing}`}
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
  return (
    <div className="mt-3 space-y-1">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-center justify-between text-xs">
          <span className="text-ink-600">{key.replaceAll("_", " ")}</span>
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
