import { getBattleSummary } from "@/lib/api";

function Meter({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div className="h-1.5 w-full rounded-full bg-ink-200 overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${
          clamped >= 100
            ? "bg-emerald-500"
            : clamped >= 50
              ? "bg-brand-500"
              : "bg-amber-500"
        }`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export async function BattleTracker() {
  let summary;
  try {
    summary = await getBattleSummary();
  } catch {
    return (
      <div className="panel p-5">
        <h3 className="text-sm font-semibold">Battle tracker</h3>
        <p className="mt-1 text-xs text-ink-500">API unreachable.</p>
      </div>
    );
  }

  const { today, goal_pct, streak_days, week_totals } = summary;

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Battle tracker</h3>
          <p className="text-[11px] text-ink-500 mt-0.5">
            Daily acquisition discipline
          </p>
        </div>
        {streak_days > 0 && (
          <span className="badge bg-amber-100 text-amber-800">
            🔥 {streak_days}-day streak
          </span>
        )}
      </div>

      <div className="p-5 space-y-4">
        <div>
          <div className="flex items-baseline justify-between mb-1.5">
            <span className="text-xs text-ink-600">
              Messages today — goal {today.goal_messages}
            </span>
            <span className="text-sm font-semibold tabular">
              {today.messages_sent}
              <span className="text-ink-400"> / {today.goal_messages}</span>
            </span>
          </div>
          <Meter pct={goal_pct} />
          <p className="mt-1 text-[11px] text-ink-500">
            {goal_pct >= 100
              ? "Goal hit. Keep going — streak continues."
              : `${today.goal_messages - today.messages_sent} more to hit goal.`}
          </p>
        </div>

        <div className="grid grid-cols-4 gap-2 pt-3 border-t border-ink-200 text-center">
          <Stat label="Calls" value={today.calls_made} />
          <Stat label="Offers" value={today.offers_made} />
          <Stat label="Appts" value={today.appointments} />
          <Stat label="Buys" value={today.purchases} />
        </div>

        <div className="pt-3 border-t border-ink-200">
          <p className="label mb-2">Last 7 days</p>
          <div className="grid grid-cols-5 gap-2 text-center">
            <Stat label="Messages" value={week_totals.messages_sent} />
            <Stat label="Calls" value={week_totals.calls_made} />
            <Stat label="Offers" value={week_totals.offers_made} />
            <Stat label="Appts" value={week_totals.appointments} />
            <Stat label="Buys" value={week_totals.purchases} />
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-sm font-semibold tabular">{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-ink-500">{label}</p>
    </div>
  );
}
