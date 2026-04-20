import Link from "next/link";
import { listListings, FsboApiError } from "@/lib/api";

interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
}

function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

async function loadStats() {
  try {
    const [privateSellers, all, dealers] = await Promise.all([
      listListings({ classification: "private_seller", limit: 1 }),
      listListings({ classification: "", limit: 1 }),
      listListings({ classification: "dealer", limit: 1 }),
    ]);
    return {
      privateTotal: privateSellers.total,
      grandTotal: all.total,
      dealerTotal: dealers.total,
      error: null as string | null,
    };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "API unreachable";
    return { privateTotal: 0, grandTotal: 0, dealerTotal: 0, error: msg };
  }
}

export default async function Home() {
  const stats = await loadStats();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-500">
          Overview of aggregated private-party listings across all sources.
        </p>
      </div>

      {stats.error && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-900/20 p-4 text-sm">
          <strong>Can&apos;t reach the FSBO API.</strong> Set{" "}
          <code className="rounded bg-slate-200 dark:bg-slate-800 px-1">FSBO_API_URL</code> and make
          sure <code className="rounded bg-slate-200 dark:bg-slate-800 px-1">fsbo-data-platform</code>{" "}
          is running. ({stats.error})
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          label="Private sellers"
          value={stats.privateTotal.toLocaleString()}
          hint="Classified as private_seller"
        />
        <StatCard label="All listings" value={stats.grandTotal.toLocaleString()} />
        <StatCard
          label="Filtered out"
          value={stats.dealerTotal.toLocaleString()}
          hint="Dealer ads removed"
        />
      </div>

      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
        <h2 className="text-lg font-semibold">Next action</h2>
        <p className="mt-1 text-sm text-slate-500">
          Browse the latest private-party listings in your target market.
        </p>
        <Link
          href="/listings"
          className="mt-4 inline-flex items-center rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          View listings →
        </Link>
      </div>
    </div>
  );
}
