import Link from "next/link";

import { type VehicleFile, formatPrice, formatRelativeDate } from "@/lib/api";

const SOURCE_LABELS: Record<string, string> = {
  craigslist: "Craigslist",
  ebay_motors: "eBay Motors",
  offerup: "OfferUp",
  ksl: "KSL",
  privateauto: "PrivateAuto",
  bring_a_trailer: "Bring a Trailer",
  recycler: "Recycler",
  hemmings: "Hemmings",
  classic_cars: "ClassicCars",
  bookoo: "Bookoo",
  el_clasificado: "El Clasificado",
  facebook_marketplace: "Facebook Marketplace",
};

export function VehicleFilePanel({
  file,
  primaryListingId,
}: {
  file: VehicleFile | null;
  primaryListingId: number;
}) {
  if (!file || file.total_sources <= 1) return null;

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold">Vehicle file</h2>
          <p className="text-[11px] text-ink-500 mt-0.5">
            This car appears on {file.total_sources} sources. Here&apos;s the
            merged history.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge bg-brand-100 text-brand-700">
            {file.total_sources} sources
          </span>
          {file.price_drop_pct !== null && file.price_drop_pct >= 1 && (
            <span className="badge bg-emerald-100 text-emerald-800">
              ↓ {file.price_drop_pct}% total drop
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 p-5 border-b border-ink-200">
        <Stat
          label="Lowest seen"
          value={formatPrice(file.min_price)}
          tone="good"
        />
        <Stat
          label="Highest asked"
          value={formatPrice(file.max_price)}
          tone="neutral"
        />
        <Stat
          label="Days on market (any)"
          value={
            file.days_on_market !== null ? `${file.days_on_market}d` : "—"
          }
          tone={
            file.days_on_market === null
              ? "neutral"
              : file.days_on_market >= 45
                ? "good"
                : "neutral"
          }
        />
      </div>

      <ul className="divide-y divide-ink-200">
        {file.sources.map((src) => {
          const isPrimary = src.id === primaryListingId;
          return (
            <li
              key={src.id}
              className={`flex items-center justify-between gap-3 px-5 py-3 text-sm ${
                isPrimary ? "bg-brand-50/50" : ""
              }`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="badge bg-ink-100 text-ink-700">
                  {SOURCE_LABELS[src.source] ?? src.source}
                </span>
                {!isPrimary && (
                  <Link
                    href={`/listings/${src.id}`}
                    className="text-ink-900 hover:text-brand-600"
                  >
                    Open in AutoCurb
                  </Link>
                )}
                {isPrimary && (
                  <span className="text-xs text-brand-700 font-medium">
                    ★ viewing this one
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 text-xs text-ink-500 tabular">
                <span className="font-semibold text-ink-900">
                  {formatPrice(src.price)}
                </span>
                <span>{formatRelativeDate(src.posted_at ?? src.first_seen_at)}</span>
                <a
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-brand-600 hover:text-brand-700"
                >
                  source ↗
                </a>
              </div>
            </li>
          );
        })}
      </ul>

      {file.price_history.length > 1 && (
        <div className="p-5 border-t border-ink-200">
          <p className="label mb-2">Price history (merged across sources)</p>
          <ul className="space-y-1">
            {file.price_history
              .slice()
              .reverse()
              .slice(0, 8)
              .map((p, idx) => (
                <li
                  key={`${p.observed_at}-${idx}`}
                  className="flex items-center justify-between text-xs tabular"
                >
                  <span className="text-ink-500">
                    {formatRelativeDate(p.observed_at)} ·{" "}
                    {SOURCE_LABELS[p.source] ?? p.source}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{formatPrice(p.price)}</span>
                    {p.delta !== null && p.delta !== 0 && (
                      <span
                        className={
                          p.delta < 0 ? "text-emerald-600" : "text-rose-600"
                        }
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
    <div className="text-center">
      <p className={`text-lg font-semibold tabular ${color}`}>{value}</p>
      <p className="mt-0.5 text-[10px] uppercase tracking-wide text-ink-500">
        {label}
      </p>
    </div>
  );
}
