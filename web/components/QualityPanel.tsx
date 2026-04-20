import type { Listing } from "@/lib/api";
import { ScoreBadge, ScoreBreakdown } from "@/components/ScoreBadge";

export function QualityPanel({ listing }: { listing: Listing }) {
  const score = listing.lead_quality_score ?? null;
  const dealerLikelihood = listing.dealer_likelihood ?? null;

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <p className="label">Lead quality</p>
        <ScoreBadge score={score} size="lg" />
      </div>

      {score !== null && (
        <p className="mt-1 text-xs text-ink-500">
          {score >= 80
            ? "Hot — call within 2 hours"
            : score >= 65
              ? "Warm — call within 24h"
              : score >= 45
                ? "Monitor — watch for price drops"
                : score >= 25
                  ? "Cold — filtered by default"
                  : "Rejected — hidden from dealer view"}
        </p>
      )}

      {listing.auto_hidden && (
        <p className="mt-2 text-[11px] rounded bg-rose-50 border border-rose-200 px-2 py-1 text-rose-700">
          Auto-hidden: {listing.auto_hide_reason ?? "hard-reject rules"}
        </p>
      )}

      <ScoreBreakdown breakdown={listing.quality_breakdown} />

      {dealerLikelihood !== null && dealerLikelihood > 0.3 && (
        <div className="mt-3 pt-3 border-t border-ink-200">
          <div className="flex items-center justify-between text-xs">
            <span className="text-ink-600">Dealer likelihood</span>
            <span
              className={`tabular font-medium ${
                dealerLikelihood >= 0.7
                  ? "text-rose-600"
                  : dealerLikelihood >= 0.4
                    ? "text-amber-600"
                    : "text-ink-600"
              }`}
            >
              {Math.round(dealerLikelihood * 100)}%
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
