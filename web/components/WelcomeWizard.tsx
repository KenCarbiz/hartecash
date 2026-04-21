"use client";

import { useState, useTransition } from "react";

interface ActionFn {
  (formData: FormData): Promise<{ ok: boolean; error?: string }>;
}

export function WelcomeWizard({
  action,
  popularMakes,
}: {
  action: ActionFn;
  popularMakes: string[];
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const toggle = (make: string) => {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(make)) next.delete(make);
      else next.add(make);
      return next;
    });
  };

  const submit = (fd: FormData) => {
    setError(null);
    for (const m of selected) fd.append("makes", m);
    startTransition(async () => {
      const res = await action(fd);
      if (!res.ok && res.error) setError(res.error);
    });
  };

  return (
    <form action={submit} className="panel p-6 space-y-5">
      <div>
        <h2 className="text-sm font-semibold">1. Where do you operate?</h2>
        <p className="text-xs text-ink-500 mt-0.5">
          We&apos;ll show listings within this radius first. You can change it later.
        </p>
        <div className="mt-3 grid grid-cols-2 gap-3 max-w-md">
          <label className="block">
            <span className="label">ZIP code</span>
            <input
              name="zip"
              required
              inputMode="numeric"
              pattern="[0-9]{5}"
              placeholder="33607"
              className="input mt-1"
            />
          </label>
          <label className="block">
            <span className="label">Radius (miles)</span>
            <select
              name="radius_miles"
              defaultValue="100"
              className="input mt-1"
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
              <option value="250">250</option>
              <option value="500">500</option>
            </select>
          </label>
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold">2. Makes you care about</h2>
        <p className="text-xs text-ink-500 mt-0.5">
          Pick any number. Leave empty to watch every make.
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {popularMakes.map((make) => {
            const active = selected.has(make);
            return (
              <button
                type="button"
                key={make}
                onClick={() => toggle(make)}
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  active
                    ? "bg-brand-600 text-white border border-brand-600"
                    : "border border-ink-200 bg-white text-ink-700 hover:bg-ink-50"
                }`}
              >
                {make}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold">3. Your budget cap (optional)</h2>
        <label className="block max-w-xs mt-2">
          <span className="label">Price ≤</span>
          <input
            name="price_max"
            type="number"
            inputMode="numeric"
            placeholder="30000"
            className="input mt-1"
          />
        </label>
      </div>

      <div className="pt-4 border-t border-ink-200">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            name="alerts_enabled"
            defaultChecked
            className="accent-brand-600 h-4 w-4"
          />
          <span className="text-sm">Email me when a hot lead matches this search</span>
        </label>
        <p className="text-[11px] text-ink-500 mt-1 ml-6">
          You can turn this off anytime in Settings → Email alerts.
        </p>
      </div>

      {error && (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {error}
        </p>
      )}

      <div className="flex items-center gap-3 pt-2">
        <button
          type="submit"
          disabled={pending}
          className="btn-primary"
        >
          {pending ? "Setting up…" : "Start watching listings"}
        </button>
        <p className="text-xs text-ink-500">
          You can add more searches later from any listing.
        </p>
      </div>
    </form>
  );
}
