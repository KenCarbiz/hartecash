"use client";

import { useTransition } from "react";

import {
  openBillingPortalAction,
  startCheckoutAction,
} from "@/app/settings/billing-actions";
import type { SubscriptionStatus } from "@/lib/api";

const PLANS = [
  {
    code: "starter" as const,
    name: "Starter",
    price: "$249",
    cadence: "/mo",
    blurb: "Solo dealership, AI voice 100 calls/day, FB Marketplace extension.",
    highlights: [
      "1 rooftop, 2 users",
      "AI vehicle vision: 5 photos / listing",
      "FB Marketplace + Craigslist scraping",
      "Self-serve, month-to-month",
    ],
  },
  {
    code: "pro" as const,
    name: "Pro",
    price: "$799",
    cadence: "/mo per rooftop",
    blurb: "Full TCPA suite, DMS push, multi-rooftop dashboard.",
    highlights: [
      "Up to 25 users",
      "Unlimited AI voice + vision",
      "DMS pushdown (Tekion, Frazer)",
      "Multi-rooftop GM dashboard",
      "TCPA compliance audit export",
    ],
    recommended: true,
  },
  {
    code: "performance" as const,
    name: "Performance",
    price: "$0",
    cadence: " + $250 / acquired vehicle",
    blurb: "Pay only when you buy. Capped at 50 acquisitions / month.",
    highlights: [
      "$0 monthly platform fee",
      "$250 metered per acquisition",
      "Same Starter capabilities",
      "50 acquisition / month cap",
    ],
  },
];

export function BillingPanel({
  subscription,
  origin,
}: {
  subscription: SubscriptionStatus | null;
  origin: string;
}) {
  const [pending, startTransition] = useTransition();

  const isActive = !!(
    subscription &&
    ["active", "trialing", "past_due"].includes(subscription.status)
  );
  const currentPlan = subscription?.plan ?? null;

  const upgrade = (plan: "starter" | "pro" | "performance") => {
    startTransition(async () => {
      const res = await startCheckoutAction(plan, origin);
      // redirect happens server-side; on error it returns
      if (res && !res.ok) alert(res.error ?? "Couldn't start checkout");
    });
  };

  const portal = () => {
    startTransition(async () => {
      const res = await openBillingPortalAction(origin);
      if (res && !res.ok) alert(res.error ?? "Portal unavailable");
    });
  };

  return (
    <div className="panel p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">Subscription</h2>
          <p className="mt-0.5 text-xs text-ink-500">
            Pay-as-you-grow. Cancel any time from the Stripe portal.
          </p>
        </div>
        {isActive && (
          <button
            type="button"
            onClick={portal}
            disabled={pending}
            className="btn-secondary text-xs"
          >
            Manage in Stripe
          </button>
        )}
      </div>

      {isActive && currentPlan && (
        <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
          Current plan: <span className="font-semibold">{currentPlan}</span>
          {subscription?.current_period_end && (
            <>
              {" "}· renews{" "}
              {new Date(subscription.current_period_end).toLocaleDateString()}
            </>
          )}
          {subscription?.cancel_at_period_end && " · cancels at period end"}
        </div>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {PLANS.map((p) => {
          const active = currentPlan === p.code && isActive;
          return (
            <div
              key={p.code}
              className={`flex flex-col rounded-md border p-4 ${
                active
                  ? "border-brand-500 bg-brand-50"
                  : p.recommended
                  ? "border-brand-300 bg-white"
                  : "border-ink-200 bg-white"
              }`}
            >
              <div className="flex items-baseline justify-between">
                <span className="text-sm font-semibold">{p.name}</span>
                {p.recommended && !active && (
                  <span className="rounded bg-brand-100 px-1.5 text-[10px] uppercase tracking-wider text-brand-700">
                    Most popular
                  </span>
                )}
                {active && (
                  <span className="rounded bg-emerald-100 px-1.5 text-[10px] uppercase tracking-wider text-emerald-700">
                    Active
                  </span>
                )}
              </div>
              <div className="mt-2">
                <span className="text-2xl font-semibold tabular">{p.price}</span>
                <span className="text-xs text-ink-500">{p.cadence}</span>
              </div>
              <p className="mt-1.5 text-xs text-ink-600">{p.blurb}</p>
              <ul className="mt-3 space-y-1 text-[11px] text-ink-700 flex-1">
                {p.highlights.map((h) => (
                  <li key={h} className="flex items-start gap-1.5">
                    <span className="mt-0.5 text-emerald-600">✓</span>
                    {h}
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={() => upgrade(p.code)}
                disabled={pending || active}
                className={`mt-3 w-full justify-center text-xs ${
                  active ? "btn-secondary" : "btn-primary"
                }`}
              >
                {active
                  ? "Current plan"
                  : isActive
                  ? "Switch"
                  : "Subscribe"}
              </button>
            </div>
          );
        })}
      </div>

      {!isActive && (
        <p className="mt-3 text-[11px] text-ink-500">
          You're on a trial / unbilled state today. Subscribe to keep
          access past your trial window.
        </p>
      )}
    </div>
  );
}
