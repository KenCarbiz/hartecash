import Link from "next/link";

import { getOnboardingChecklist, type OnboardingItem } from "@/lib/api";

const ROUTES: Record<string, string> = {
  twilio: "/settings",
  team_member: "/settings",
  routing: "/settings",
  extension: "/settings",
  saved_search: "/welcome",
  first_lead: "/listings",
  webhook: "/settings",
  subscription: "/settings",
};

export async function OnboardingPanel() {
  let checklist;
  try {
    checklist = await getOnboardingChecklist();
  } catch {
    return null;
  }
  if (!checklist) return null;

  const { items, completed, total } = checklist;
  // Hide once everything's done. The panel is meant for first-run /
  // mid-setup, not as permanent dashboard chrome.
  if (completed >= total) return null;

  const pct = Math.round((completed / total) * 100);

  return (
    <div className="panel mb-6">
      <div className="panel-header flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Setup checklist</h3>
          <p className="text-[11px] text-ink-500 mt-0.5">
            Complete these to get the most out of AutoAcquisition.
          </p>
        </div>
        <span className="text-sm font-semibold tabular">
          {completed}
          <span className="text-ink-400"> / {total}</span>
        </span>
      </div>

      <div className="px-5 pt-3">
        <div className="h-1.5 w-full rounded-full bg-ink-200 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              pct >= 100 ? "bg-emerald-500" : pct >= 50 ? "bg-brand-500" : "bg-amber-500"
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <ul className="divide-y divide-ink-200 mt-3">
        {items.map((item) => (
          <ChecklistRow key={item.key} item={item} />
        ))}
      </ul>
    </div>
  );
}

function ChecklistRow({ item }: { item: OnboardingItem }) {
  const href = ROUTES[item.key] ?? "/settings";
  return (
    <li className="flex items-start gap-3 px-5 py-3">
      <span
        className={`mt-0.5 inline-flex h-5 w-5 flex-none items-center justify-center rounded-full text-[11px] font-semibold ${
          item.done
            ? "bg-emerald-100 text-emerald-700"
            : "bg-ink-100 text-ink-500"
        }`}
        aria-label={item.done ? "Done" : "Not done"}
      >
        {item.done ? "✓" : ""}
      </span>
      <div className="min-w-0 flex-1">
        <p
          className={`text-sm ${
            item.done ? "text-ink-500 line-through" : "font-medium text-ink-900"
          }`}
        >
          {item.label}
        </p>
        {!item.done && item.detail && (
          <p className="mt-0.5 text-xs text-ink-500">{item.detail}</p>
        )}
      </div>
      {!item.done && (
        <Link
          href={href}
          className="text-xs font-medium text-brand-600 hover:text-brand-700 flex-none"
        >
          Set up →
        </Link>
      )}
    </li>
  );
}
