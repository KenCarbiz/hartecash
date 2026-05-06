"use client";

import { useTransition } from "react";

import { refreshHistoryReportAction } from "@/app/listings/[id]/history-actions";
import { formatRelativeDate, type HistoryReport } from "@/lib/api";

const TITLE_TONE: Record<string, string> = {
  clean: "bg-emerald-100 text-emerald-800 border-emerald-200",
  salvage: "bg-rose-100 text-rose-800 border-rose-200",
  rebuilt: "bg-amber-100 text-amber-800 border-amber-200",
  flood: "bg-rose-100 text-rose-800 border-rose-200",
  lemon: "bg-rose-100 text-rose-800 border-rose-200",
  junk: "bg-rose-200 text-rose-900 border-rose-300",
  theft_reported: "bg-rose-200 text-rose-900 border-rose-300",
  manufacturer_buyback: "bg-amber-100 text-amber-800 border-amber-200",
  odometer_rollback: "bg-rose-200 text-rose-900 border-rose-300",
  unknown: "bg-ink-100 text-ink-700 border-ink-200",
};

const SOURCE_LABEL: Record<string, string> = {
  carfax: "CARFAX",
  autocheck: "AutoCheck",
  nmvtis: "NMVTIS",
  none: "—",
  stub: "Stub",
};

export function HistoryReportPanel({
  listingId,
  hasVin,
  report,
}: {
  listingId: number;
  hasVin: boolean;
  report: HistoryReport | null;
}) {
  const [pending, startTransition] = useTransition();

  const refresh = () => {
    startTransition(async () => {
      const res = await refreshHistoryReportAction(listingId);
      if (!res.ok) alert(res.error ?? "refresh failed");
    });
  };

  if (!hasVin) {
    return (
      <div className="panel">
        <div className="panel-header">
          <h3 className="text-sm font-semibold">Vehicle history</h3>
        </div>
        <p className="px-5 py-4 text-xs text-ink-500">
          Add a VIN above to pull a history report.
        </p>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="panel">
        <div className="panel-header flex items-center justify-between">
          <h3 className="text-sm font-semibold">Vehicle history</h3>
          <button
            type="button"
            onClick={refresh}
            disabled={pending}
            className="btn-secondary text-xs"
          >
            {pending ? "Pulling…" : "Pull report"}
          </button>
        </div>
        <p className="px-5 py-4 text-xs text-ink-500">
          Click <strong>Pull report</strong> to query the configured
          provider (CARFAX, AutoCheck, or NMVTIS).
        </p>
      </div>
    );
  }

  const showTimeline = report.events && report.events.length > 0;
  const blocked = report.status !== "ok";

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Vehicle history</h3>
          <p className="text-[11px] text-ink-500 mt-0.5 tabular">
            {SOURCE_LABEL[report.source] ?? report.source}
            {report.fetched_at && (
              <> · pulled {formatRelativeDate(report.fetched_at)}</>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={pending}
          className="btn-secondary text-xs"
        >
          {pending ? "Pulling…" : "Refresh"}
        </button>
      </div>

      {blocked ? (
        <div className="px-5 py-4 space-y-2 text-xs">
          <p className="font-medium text-amber-800">
            {humanStatus(report.status)}
          </p>
          {report.error_detail && (
            <p className="text-ink-600">{report.error_detail}</p>
          )}
        </div>
      ) : (
        <div className="space-y-3 p-4">
          <div className="flex flex-wrap gap-1.5">
            <Chip
              label="Title"
              value={report.title_brand.replace(/_/g, " ")}
              tone={TITLE_TONE[report.title_brand] ?? TITLE_TONE.unknown}
            />
            {report.accident_count != null && (
              <Chip
                label="Accidents"
                value={String(report.accident_count)}
                tone={
                  report.accident_count > 0
                    ? "bg-rose-50 text-rose-800 border-rose-200"
                    : "bg-emerald-100 text-emerald-800 border-emerald-200"
                }
              />
            )}
            {report.owner_count != null && (
              <Chip label="Owners" value={String(report.owner_count)} />
            )}
            {report.open_recall_count != null && report.open_recall_count > 0 && (
              <Chip
                label="Open recalls"
                value={String(report.open_recall_count)}
                tone="bg-amber-50 text-amber-800 border-amber-200"
              />
            )}
            {report.service_record_count != null && (
              <Chip
                label="Service"
                value={String(report.service_record_count)}
              />
            )}
            {report.use_type && (
              <Chip label="Use" value={report.use_type} />
            )}
            {report.last_reported_mileage != null && (
              <Chip
                label="Last odo"
                value={`${report.last_reported_mileage.toLocaleString()} mi`}
              />
            )}
          </div>

          {showTimeline && (
            <details className="rounded-md border border-ink-200 bg-white">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-ink-700">
                Timeline ({report.events.length} events)
              </summary>
              <ol className="max-h-60 overflow-y-auto divide-y divide-ink-100 px-3 pb-2 pt-1 text-xs">
                {report.events.map((e, idx) => (
                  <li key={idx} className="py-1.5">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="font-medium text-ink-700 capitalize">
                        {e.kind.replace(/_/g, " ")}
                      </span>
                      <time className="text-[10px] tabular text-ink-500">
                        {e.when}
                      </time>
                    </div>
                    {e.description && (
                      <p className="mt-0.5 text-ink-700">{e.description}</p>
                    )}
                    {e.location && (
                      <p className="mt-0.5 text-[11px] text-ink-500">
                        {e.location}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            </details>
          )}

          {report.full_report_url && (
            <a
              href={report.full_report_url}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-center text-[11px] text-brand-600 hover:text-brand-700"
            >
              Open full report ↗
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function humanStatus(status: string): string {
  switch (status) {
    case "no_provider_configured":
      return "No history provider configured.";
    case "vin_not_found":
      return "Provider didn't recognize this VIN.";
    case "provider_error":
      return "Provider returned an error. Try again or check the API key.";
    case "invalid_vin":
      return "VIN must be 17 characters.";
    default:
      return status;
  }
}

function Chip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] ${
        tone ?? "bg-white text-ink-700 border-ink-200"
      }`}
    >
      <span className="text-[9px] uppercase tracking-wider opacity-70">
        {label}
      </span>
      <span className="font-medium capitalize">{value}</span>
    </span>
  );
}
