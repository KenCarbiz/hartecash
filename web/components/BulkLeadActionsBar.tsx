"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import {
  bulkArchiveAction,
  bulkAssignAction,
  bulkStatusAction,
} from "@/app/leads/bulk-actions";
import type { LeadStatus, Teammate } from "@/lib/api";

const STATUS_OPTIONS: LeadStatus[] = [
  "new",
  "contacted",
  "negotiating",
  "appointment",
  "purchased",
  "lost",
];

export function BulkLeadActionsBar({
  selected,
  teammates,
  onClear,
}: {
  selected: number[];
  teammates: Teammate[];
  onClear: () => void;
}) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<string | null>(null);
  const router = useRouter();

  const run = (
    fn: () => Promise<{
      ok: boolean;
      updated?: number;
      skipped?: number;
      error?: string;
    }>,
  ) => {
    setResult(null);
    startTransition(async () => {
      const out = await fn();
      if (out.ok) {
        setResult(
          `✓ ${out.updated ?? 0} updated${out.skipped ? `, ${out.skipped} skipped` : ""}.`,
        );
        router.refresh();
        onClear();
      } else {
        setResult(`⚠ ${out.error}`);
      }
    });
  };

  const onStatusChange = (status: LeadStatus) =>
    run(() => bulkStatusAction(selected, status));
  const onAssign = (assignedTo: string | null) =>
    run(() => bulkAssignAction(selected, assignedTo));
  const onArchive = () =>
    run(() => bulkArchiveAction(selected, "bulk archive"));

  if (selected.length === 0 && !result) return null;

  return (
    <div className="sticky bottom-4 z-20 mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ink-200 bg-ink-900 px-4 py-3 text-white shadow-lg">
      <div className="flex items-center gap-3 text-sm">
        <span className="tabular font-semibold">{selected.length}</span>
        <span className="text-ink-300">selected</span>
        {result && (
          <span
            className={`text-xs ${
              result.startsWith("⚠") ? "text-rose-300" : "text-emerald-300"
            }`}
          >
            {result}
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SelectControl
          ariaLabel="Set status"
          placeholder="Set status…"
          disabled={pending || selected.length === 0}
          onChange={(v) => v && onStatusChange(v as LeadStatus)}
          options={STATUS_OPTIONS.map((s) => ({ value: s, label: s.replace("_", " ") }))}
        />
        <SelectControl
          ariaLabel="Reassign"
          placeholder="Reassign…"
          disabled={pending || selected.length === 0}
          onChange={(v) => onAssign(v || null)}
          options={[
            { value: "", label: "(unassigned)" },
            ...teammates.map((t) => ({ value: t.email, label: t.email })),
          ]}
        />
        <button
          onClick={onArchive}
          disabled={pending || selected.length === 0}
          className="rounded-md border border-rose-500/40 bg-rose-600/20 px-3 py-1.5 text-xs font-medium text-rose-200 hover:bg-rose-600/40"
        >
          {pending ? "…" : "Archive"}
        </button>
        <button
          onClick={onClear}
          className="rounded-md border border-ink-700 px-3 py-1.5 text-xs text-ink-300 hover:bg-ink-800"
        >
          Clear
        </button>
      </div>
    </div>
  );
}

function SelectControl({
  ariaLabel,
  placeholder,
  options,
  onChange,
  disabled,
}: {
  ariaLabel: string;
  placeholder: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <select
      aria-label={ariaLabel}
      disabled={disabled}
      defaultValue=""
      onChange={(e) => {
        const v = e.target.value;
        if (v === "__placeholder__") return;
        onChange(v);
        e.currentTarget.value = "__placeholder__";
      }}
      className="rounded-md border border-ink-700 bg-ink-800 px-3 py-1.5 text-xs text-white disabled:opacity-50"
    >
      <option value="__placeholder__">{placeholder}</option>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
