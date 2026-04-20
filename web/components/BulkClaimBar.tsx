"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { bulkClaimAction } from "@/app/listings/bulk-actions";

interface BulkClaimBarProps {
  selected: number[];
  onClear: () => void;
}

export function BulkClaimBar({ selected, onClear }: BulkClaimBarProps) {
  const [assignedTo, setAssignedTo] = useState("");
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<string | null>(null);
  const router = useRouter();

  const claim = () => {
    if (selected.length === 0) return;
    startTransition(async () => {
      const out = await bulkClaimAction(selected, assignedTo || undefined);
      if ("claimed" in out) {
        setResult(
          `${out.claimed} claimed${
            out.already_claimed ? `, ${out.already_claimed} already yours` : ""
          }.`,
        );
        router.refresh();
        onClear();
      } else {
        setResult(`⚠ ${out.error}`);
      }
    });
  };

  if (selected.length === 0 && !result) return null;

  return (
    <div className="sticky bottom-4 z-20 mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-ink-200 bg-ink-900 px-4 py-3 text-white shadow-lg">
      <div className="flex items-center gap-3 text-sm">
        <span className="tabular font-semibold">{selected.length}</span>
        <span className="text-ink-300">selected</span>
        {result && <span className="text-emerald-300 text-xs">{result}</span>}
      </div>
      <div className="flex items-center gap-2">
        <input
          type="text"
          placeholder="Assign to (optional)"
          value={assignedTo}
          onChange={(e) => setAssignedTo(e.target.value)}
          className="rounded-md border border-ink-700 bg-ink-800 px-3 py-1.5 text-sm text-white placeholder:text-ink-500"
        />
        <button onClick={claim} disabled={pending} className="btn-primary text-xs">
          {pending ? "Claiming…" : `Claim ${selected.length}`}
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
