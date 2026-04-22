"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { patchFactsAction } from "@/app/listings/[id]/facts-actions";

// Minimal dropdown of US states + territories for the plate state picker.
const STATES = [
  "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
  "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
  "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
  "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
  "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
  "DC", "PR",
];

export function VehicleFactsEditor({
  listingId,
  initial,
}: {
  listingId: number;
  initial: {
    license_plate?: string | null;
    license_plate_state?: string | null;
    color?: string | null;
    vin?: string | null;
    drivable?: boolean | null;
  };
}) {
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [plate, setPlate] = useState(initial.license_plate ?? "");
  const [state, setState] = useState(initial.license_plate_state ?? "");
  const [color, setColor] = useState(initial.color ?? "");
  const [vin, setVin] = useState(initial.vin ?? "");
  const [drivable, setDrivable] = useState<"yes" | "no" | "unknown">(
    initial.drivable === true ? "yes" : initial.drivable === false ? "no" : "unknown",
  );
  const router = useRouter();

  const submit = (fd: FormData) => {
    setError(null);
    startTransition(async () => {
      const res = await patchFactsAction(fd);
      if (!res.ok) setError(res.error ?? "save failed");
      else {
        setOpen(false);
        router.refresh();
      }
    });
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-xs text-brand-600 hover:text-brand-700 font-medium"
      >
        Edit plate / color / VIN / drivable
      </button>
    );
  }

  return (
    <form
      action={submit}
      className="mt-2 rounded-md border border-ink-200 bg-ink-50 p-3 space-y-2"
    >
      <input type="hidden" name="listing_id" value={listingId} />

      <div className="grid grid-cols-3 gap-2">
        <label className="col-span-1">
          <span className="label">Plate state</span>
          <select
            name="license_plate_state"
            value={state}
            onChange={(e) => setState(e.target.value.toUpperCase())}
            className="input mt-1"
          >
            <option value="">—</option>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="col-span-2">
          <span className="label">Plate number</span>
          <input
            name="license_plate"
            value={plate}
            onChange={(e) => setPlate(e.target.value.toUpperCase())}
            placeholder="ABC 1234"
            maxLength={16}
            className="input mt-1 font-mono"
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="label">Color</span>
          <input
            name="color"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            placeholder="e.g. Graphite Grey"
            maxLength={32}
            className="input mt-1"
          />
        </label>
        <label className="block">
          <span className="label">VIN</span>
          <input
            name="vin"
            value={vin}
            onChange={(e) => setVin(e.target.value.toUpperCase())}
            placeholder="17 chars"
            maxLength={17}
            className="input mt-1 font-mono"
          />
        </label>
      </div>

      <div>
        <span className="label">Drivable</span>
        <div className="mt-1 flex items-center gap-3 text-xs">
          {(["yes", "no", "unknown"] as const).map((v) => (
            <label key={v} className="inline-flex items-center gap-1">
              <input
                type="radio"
                name="drivable"
                value={v}
                checked={drivable === v}
                onChange={() => setDrivable(v)}
              />
              <span className="capitalize">{v}</span>
            </label>
          ))}
        </div>
      </div>

      {error && (
        <p className="text-[11px] text-rose-700">⚠ {error}</p>
      )}

      <div className="flex items-center gap-2 pt-1">
        <button
          type="submit"
          disabled={pending}
          className="btn-primary text-xs"
        >
          {pending ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="btn-secondary text-xs"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}


/** Compact plate chip for prominent header display. Yellow-on-black
 *  to mimic a real plate; hidden entirely when plate isn't set. */
export function PlateChip({
  plate,
  state,
}: {
  plate: string | null | undefined;
  state: string | null | undefined;
}) {
  if (!plate) return null;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md bg-ink-900 text-amber-300 font-mono text-xs px-2 py-1 border-2 border-ink-700"
      title="License plate"
    >
      {state && (
        <span className="text-[9px] uppercase tracking-wider text-amber-400/80 leading-none">
          {state}
        </span>
      )}
      <span className="leading-none">{plate}</span>
    </span>
  );
}
