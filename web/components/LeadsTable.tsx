"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { AssigneeDropdown } from "@/components/AssigneeDropdown";
import { BulkLeadActionsBar } from "@/components/BulkLeadActionsBar";
import {
  formatDuration,
  formatMileage,
  formatPrice,
  formatRelativeDate,
  isLeadUnread,
  type Lead,
  type LeadStatus,
  type Teammate,
} from "@/lib/api";

const STATUS_STYLES: Record<LeadStatus, string> = {
  new: "bg-ink-100 text-ink-700",
  contacted: "bg-sky-100 text-sky-800",
  negotiating: "bg-indigo-100 text-indigo-800",
  appointment: "bg-violet-100 text-violet-800",
  purchased: "bg-emerald-100 text-emerald-800",
  lost: "bg-rose-100 text-rose-800",
};

export function LeadsTable({
  leads,
  teammates,
}: {
  leads: Lead[];
  teammates: Teammate[];
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const allIds = useMemo(() => leads.map((l) => l.id), [leads]);
  const allSelected = selected.size > 0 && selected.size === allIds.length;
  const someSelected = selected.size > 0 && !allSelected;

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(allIds));
    }
  };

  const toggleOne = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <>
      <div className="panel overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="px-4 py-2.5 w-9">
                <input
                  type="checkbox"
                  className="accent-brand-600 h-4 w-4"
                  checked={allSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someSelected;
                  }}
                  onChange={toggleAll}
                  aria-label="Select all leads"
                />
              </th>
              <th className="text-left font-medium px-4 py-2.5">Vehicle</th>
              <th className="text-left font-medium px-4 py-2.5">Location</th>
              <th className="text-right font-medium px-4 py-2.5">Mileage</th>
              <th className="text-right font-medium px-4 py-2.5">Price</th>
              <th className="text-left font-medium px-4 py-2.5">Assigned</th>
              <th className="text-left font-medium px-4 py-2.5">Status</th>
              <th
                className="text-right font-medium px-4 py-2.5"
                title="Time from lead creation to first outbound contact"
              >
                First touch
              </th>
              <th className="text-right font-medium px-4 py-2.5">Updated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-200">
            {leads.map((l) => {
              const vehicle =
                [l.listing_year, l.listing_make, l.listing_model]
                  .filter(Boolean)
                  .join(" ") || l.listing_title || "—";
              const loc =
                [l.listing_city, l.listing_state].filter(Boolean).join(", ") ||
                l.listing_zip ||
                "—";
              const unread = isLeadUnread(l);
              const isSelected = selected.has(l.id);
              return (
                <tr
                  key={l.id}
                  className={`hover:bg-ink-50 ${
                    isSelected ? "bg-brand-50" : unread ? "bg-amber-50/50" : ""
                  }`}
                >
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      className="accent-brand-600 h-4 w-4"
                      checked={isSelected}
                      onChange={() => toggleOne(l.id)}
                      aria-label={`Select lead ${l.id}`}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/listings/${l.listing_id}`}
                      className="flex items-center gap-2 font-medium text-ink-900 hover:text-brand-600"
                    >
                      {unread && (
                        <span
                          className="inline-block h-2 w-2 flex-none rounded-full bg-rose-500"
                          title="New seller reply"
                          aria-label="New seller reply"
                        />
                      )}
                      <span className={unread ? "font-semibold" : ""}>
                        {vehicle}
                      </span>
                    </Link>
                    <p className="mt-0.5 text-xs text-ink-500">
                      {l.listing_source ?? "—"}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-ink-700">{loc}</td>
                  <td className="px-4 py-3 text-right tabular text-ink-700">
                    {formatMileage(l.listing_mileage ?? null)}
                  </td>
                  <td className="px-4 py-3 text-right tabular font-semibold">
                    {formatPrice(l.listing_price ?? null)}
                  </td>
                  <td className="px-4 py-3">
                    <AssigneeDropdown
                      leadId={l.id}
                      current={l.assigned_to}
                      teammates={teammates}
                      compact
                    />
                  </td>
                  <td className="px-4 py-3">
                    <span className={`badge ${STATUS_STYLES[l.status]}`}>
                      {l.status.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-xs tabular">
                    <FirstTouch
                      createdAt={l.created_at}
                      firstRespondedAt={l.first_responded_at ?? null}
                      status={l.status}
                    />
                  </td>
                  <td className="px-4 py-3 text-right text-xs text-ink-500 tabular">
                    {formatRelativeDate(l.updated_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <BulkLeadActionsBar
        selected={Array.from(selected)}
        teammates={teammates}
        onClear={() => setSelected(new Set())}
      />
    </>
  );
}

function FirstTouch({
  createdAt,
  firstRespondedAt,
  status,
}: {
  createdAt: string;
  firstRespondedAt: string | null;
  status: LeadStatus;
}) {
  if (firstRespondedAt) {
    const minutes = Math.max(
      0,
      Math.round(
        (new Date(firstRespondedAt).getTime() - new Date(createdAt).getTime()) /
          60000,
      ),
    );
    const tone =
      minutes <= 5
        ? "text-emerald-700"
        : minutes <= 60
          ? "text-ink-600"
          : "text-amber-700";
    return <span className={tone}>{formatDuration(minutes)}</span>;
  }
  if (status === "purchased" || status === "lost") {
    return <span className="text-ink-400">—</span>;
  }
  const stale = Math.round(
    (Date.now() - new Date(createdAt).getTime()) / 60000,
  );
  const tone =
    stale > 60 ? "text-rose-700" : stale > 5 ? "text-amber-700" : "text-ink-500";
  return <span className={tone}>not yet</span>;
}
