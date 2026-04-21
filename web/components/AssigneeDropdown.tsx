"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { reassignLeadAction } from "@/app/leads/actions";
import type { Teammate } from "@/lib/api";

export function AssigneeDropdown({
  leadId,
  current,
  teammates,
  compact = false,
}: {
  leadId: number;
  current: string | null;
  teammates: Teammate[];
  compact?: boolean;
}) {
  const [value, setValue] = useState(current ?? "");
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const onChange = (next: string) => {
    setValue(next);
    startTransition(async () => {
      const fd = new FormData();
      fd.set("lead_id", String(leadId));
      fd.set("assigned_to", next);
      await reassignLeadAction(fd);
      router.refresh();
    });
  };

  const size = compact
    ? "text-xs py-0.5 px-2 max-w-[140px]"
    : "text-sm py-1.5 px-2 w-full";

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={pending}
      className={`rounded-md border border-ink-300 bg-white text-ink-800 ${size}`}
      aria-label={`Assignee for lead ${leadId}`}
    >
      <option value="">Unassigned</option>
      {teammates.map((t) => {
        const label = t.name ? `${t.name} (${t.email})` : t.email;
        return (
          <option key={t.email} value={t.email}>
            {label}
          </option>
        );
      })}
      {/* Preserve existing value even if it's not in teammates (e.g. free-form) */}
      {value && !teammates.some((t) => t.email === value) && (
        <option value={value}>{value}</option>
      )}
    </select>
  );
}
