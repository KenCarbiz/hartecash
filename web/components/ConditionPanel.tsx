"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import type { ConditionAssessment, ConditionRating, DamageLevel } from "@/lib/api";

const RATING_COLOR: Record<ConditionRating, string> = {
  excellent: "bg-emerald-100 text-emerald-800 border-emerald-200",
  good: "bg-emerald-50 text-emerald-700 border-emerald-200",
  fair: "bg-amber-50 text-amber-800 border-amber-200",
  poor: "bg-rose-50 text-rose-800 border-rose-200",
  unknown: "bg-ink-100 text-ink-600 border-ink-200",
};

const DAMAGE_COLOR: Record<DamageLevel, string> = {
  none: "bg-emerald-100 text-emerald-800 border-emerald-200",
  cosmetic: "bg-amber-50 text-amber-800 border-amber-200",
  moderate: "bg-orange-50 text-orange-800 border-orange-200",
  heavy: "bg-rose-100 text-rose-800 border-rose-200",
  unknown: "bg-ink-100 text-ink-600 border-ink-200",
};

export function ConditionPanel({ condition }: { condition?: ConditionAssessment }) {
  const router = useRouter();
  const pending = !condition || !condition.checked_images;

  useEffect(() => {
    if (!pending) return;
    // Poll the page every 8s — server-component data refetches and the
    // panel re-renders with the assessment once vision finishes. Stops
    // automatically when checked_images > 0.
    const id = setInterval(() => router.refresh(), 8000);
    return () => clearInterval(id);
  }, [pending, router]);

  if (pending) {
    return (
      <div className="panel">
        <div className="panel-header">
          <h3 className="text-sm font-semibold">AI condition</h3>
        </div>
        <p className="px-5 py-4 text-xs text-ink-500">
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500 mr-1.5 align-middle" />
          Claude vision running on photos…
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <h3 className="text-sm font-semibold">AI condition</h3>
        <span className="text-[10px] uppercase tracking-wider text-ink-500">
          Claude vision · {condition.checked_images} photo{condition.checked_images === 1 ? "" : "s"}
        </span>
      </div>
      <div className="space-y-3 p-4">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <Chip label="Overall" value={condition.overall ?? "unknown"} kind="rating" />
          <Chip label="Body damage" value={condition.body_damage ?? "unknown"} kind="damage" />
          <Chip label="Paint" value={condition.paint ?? "unknown"} kind="rating" />
          <Chip label="Interior" value={condition.interior ?? "unknown"} kind="rating" />
          <Chip label="Tires" value={condition.tires ?? "unknown"} kind="rating" />
        </div>

        {condition.flags && condition.flags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {condition.flags.map((f) => (
              <span
                key={f}
                className="rounded bg-rose-50 border border-rose-200 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-rose-800"
              >
                {f.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}

        {condition.notes && (
          <p className="rounded-md border border-ink-200 bg-ink-50 px-3 py-2 text-xs text-ink-700 leading-relaxed">
            {condition.notes}
          </p>
        )}
      </div>
    </div>
  );
}

function Chip({
  label,
  value,
  kind,
}: {
  label: string;
  value: string;
  kind: "rating" | "damage";
}) {
  const palette =
    kind === "rating"
      ? RATING_COLOR[value as ConditionRating] ?? RATING_COLOR.unknown
      : DAMAGE_COLOR[value as DamageLevel] ?? DAMAGE_COLOR.unknown;
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-ink-200 bg-white px-2 py-1.5">
      <span className="text-[10px] uppercase tracking-wider text-ink-500">
        {label}
      </span>
      <span
        className={`rounded border px-1.5 py-0.5 text-[11px] capitalize ${palette}`}
      >
        {value}
      </span>
    </div>
  );
}
