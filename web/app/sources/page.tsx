import { PageHeader } from "@/components/AppShell";
import {
  formatRelativeDate,
  getScrapeRuns,
  getSourceHealth,
} from "@/lib/api";

export const dynamic = "force-dynamic";

const KNOWN_SOURCES = [
  {
    key: "craigslist",
    label: "Craigslist",
    status: "live",
    description: "RSS feeds per city. Polite rate limit.",
  },
  {
    key: "ebay_motors",
    label: "eBay Motors",
    status: "live",
    description: "Official Browse API. Requires EBAY_APP_ID + EBAY_CERT_ID.",
  },
  {
    key: "offerup",
    label: "OfferUp",
    status: "proxy-required",
    description: "Set PROXY_URL and legal-review before enabling.",
  },
  {
    key: "ksl",
    label: "KSL Classifieds",
    status: "live",
    description: "Intermountain West FSBO (UT/ID/WY/NV). JSON-LD Vehicle blocks.",
  },
  {
    key: "privateauto",
    label: "PrivateAuto",
    status: "live",
    description: "100% FSBO platform (founded 2022). Parses __NEXT_DATA__.",
  },
  {
    key: "bring_a_trailer",
    label: "Bring a Trailer",
    status: "live",
    description: "Enthusiast auctions. Walks index + fetches per-listing JSON-LD.",
  },
  {
    key: "facebook_marketplace",
    label: "Facebook Marketplace",
    status: "extension",
    description: "Via AutoCurb Chrome extension on dealer's browser.",
  },
];

const STATUS_STYLE: Record<string, string> = {
  live: "bg-emerald-100 text-emerald-800 border-emerald-200",
  "proxy-required": "bg-amber-100 text-amber-800 border-amber-200",
  extension: "bg-sky-100 text-sky-800 border-sky-200",
  planned: "bg-ink-100 text-ink-600 border-ink-200",
};

export default async function SourcesPage() {
  const [health, runs] = await Promise.all([
    getSourceHealth(),
    getScrapeRuns(),
  ]);
  const healthByKey = Object.fromEntries(health.map((h) => [h.source, h]));

  return (
    <>
      <PageHeader
        title="Sources"
        subtitle={`${KNOWN_SOURCES.filter((s) => s.status === "live").length} live sources · ${health.reduce((acc, h) => acc + h.total_listings, 0).toLocaleString()} total listings`}
      />

      <div className="panel overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="text-left font-medium px-4 py-2.5">Source</th>
              <th className="text-left font-medium px-4 py-2.5">Status</th>
              <th className="text-right font-medium px-4 py-2.5">Total</th>
              <th className="text-right font-medium px-4 py-2.5">Last 24h</th>
              <th className="text-right font-medium px-4 py-2.5">Last 7d</th>
              <th className="text-right font-medium px-4 py-2.5">Last run</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-200">
            {KNOWN_SOURCES.map((s) => {
              const h = healthByKey[s.key];
              return (
                <tr key={s.key} className="hover:bg-ink-50">
                  <td className="px-4 py-3">
                    <p className="font-medium">{s.label}</p>
                    <p className="text-xs text-ink-500 mt-0.5">{s.description}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`badge border ${
                        STATUS_STYLE[s.status] ?? STATUS_STYLE.planned
                      }`}
                    >
                      {s.status.replace("-", " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular">
                    {(h?.total_listings ?? 0).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right tabular">
                    {(h?.listings_last_24h ?? 0).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right tabular">
                    {(h?.listings_last_7d ?? 0).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right text-xs text-ink-500 tabular">
                    {formatRelativeDate(h?.last_scrape_at ?? null)}
                    {h?.last_scrape_error && (
                      <span className="ml-1 text-rose-600" title={h.last_scrape_error}>
                        ⚠
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-semibold">Recent scrape runs</h2>
        </div>
        {runs.length === 0 ? (
          <p className="p-5 text-sm text-ink-500">
            No scrape runs recorded yet. Start the scheduler or run{" "}
            <code className="rounded bg-ink-100 px-1">
              python -m fsbo.workers.poll --source craigslist --city tampa
            </code>
            .
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="text-left font-medium px-4 py-2.5">Source</th>
                <th className="text-left font-medium px-4 py-2.5">When</th>
                <th className="text-right font-medium px-4 py-2.5">Fetched</th>
                <th className="text-right font-medium px-4 py-2.5">New</th>
                <th className="text-right font-medium px-4 py-2.5">Updated</th>
                <th className="text-left font-medium px-4 py-2.5">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {runs.map((r) => (
                <tr key={r.id} className="hover:bg-ink-50">
                  <td className="px-4 py-2.5">{r.source}</td>
                  <td className="px-4 py-2.5 text-xs text-ink-500 tabular">
                    {formatRelativeDate(r.started_at)}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular">{r.fetched_count}</td>
                  <td className="px-4 py-2.5 text-right tabular text-emerald-600">
                    {r.inserted_count}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular text-ink-600">
                    {r.updated_count}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-rose-600 truncate max-w-md">
                    {r.error ?? ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
