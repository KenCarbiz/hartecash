import type { LeaderboardResponse } from "@/lib/api";

/** Per-rep leaderboard. Renders raw counts so the dealer reads the
 *  funnel as a wide table; the score column drives the default sort.
 *  Layout is intentionally minimal until the dashboard design pass. */
export function LeaderboardPanel({
  leaderboard,
  days,
}: {
  leaderboard: LeaderboardResponse | null;
  days: number;
}) {
  if (!leaderboard || leaderboard.reps.length === 0) {
    return (
      <div className="panel p-5">
        <h2 className="text-sm font-semibold">Per-rep leaderboard</h2>
        <p className="mt-2 text-xs text-ink-500">
          No claimed leads in the last {days} days. Once your team starts
          claiming leads they'll appear here ranked by acquisition score.
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">Per-rep leaderboard</h2>
          <p className="text-[11px] text-ink-500 mt-0.5 tabular">
            Last {days} days · ranked by 5×purchases + 2×appointments + contacts
          </p>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="px-3 py-2.5 text-left">Rep</th>
              <th className="px-2 py-2.5 text-right">Score</th>
              <th className="px-2 py-2.5 text-right">Claimed</th>
              <th className="px-2 py-2.5 text-right">Contacted</th>
              <th className="px-2 py-2.5 text-right">Appts</th>
              <th className="px-2 py-2.5 text-right">Purchases</th>
              <th className="px-2 py-2.5 text-right">SMS</th>
              <th className="px-2 py-2.5 text-right">Calls</th>
              <th className="px-2 py-2.5 text-right">Offers</th>
              <th className="px-2 py-2.5 text-right">1st reply</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {leaderboard.reps.map((r, idx) => (
              <tr key={r.assigned_to} className={idx === 0 ? "bg-emerald-50/40" : ""}>
                <td className="px-3 py-2 text-ink-900">
                  {r.assigned_to === "(unassigned)" ? (
                    <span className="text-ink-500 italic">Unassigned</span>
                  ) : (
                    r.assigned_to
                  )}
                </td>
                <td className="px-2 py-2 text-right tabular font-medium">
                  {r.score}
                </td>
                <td className="px-2 py-2 text-right tabular">{r.leads_claimed}</td>
                <td className="px-2 py-2 text-right tabular">{r.leads_contacted}</td>
                <td className="px-2 py-2 text-right tabular">{r.leads_appointment}</td>
                <td className="px-2 py-2 text-right tabular">
                  <span className={r.leads_purchased > 0 ? "font-semibold text-emerald-700" : ""}>
                    {r.leads_purchased}
                  </span>
                </td>
                <td className="px-2 py-2 text-right tabular">{r.sms_sent}</td>
                <td className="px-2 py-2 text-right tabular">{r.voice_calls}</td>
                <td className="px-2 py-2 text-right tabular">
                  {r.offers_accepted > 0 ? (
                    <>
                      {r.offers_sent}{" "}
                      <span className="text-emerald-700 font-medium">
                        ✓{r.offers_accepted}
                      </span>
                    </>
                  ) : (
                    r.offers_sent
                  )}
                </td>
                <td className="px-2 py-2 text-right tabular text-ink-600">
                  {r.avg_response_minutes != null
                    ? `${formatMinutes(r.avg_response_minutes)}`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatMinutes(m: number): string {
  if (m < 1) return "<1m";
  if (m < 60) return `${Math.round(m)}m`;
  const hours = Math.floor(m / 60);
  const minutes = Math.round(m - hours * 60);
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}
