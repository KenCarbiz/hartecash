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
            ? "Hot — call immediately"
            : score >= 60
              ? "Warm — text within 1 hour"
              : score >= 40
                ? "Monitor — watch for price drops"
                : "Cold — likely not worth pursuing"}
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
