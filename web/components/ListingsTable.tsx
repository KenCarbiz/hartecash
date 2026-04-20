"use client";

import Link from "next/link";
import { useState } from "react";

import { BulkClaimBar } from "@/components/BulkClaimBar";
import {
  type Listing,
  formatMileage,
  formatPrice,
  formatRelativeDate,
} from "@/lib/api";

const CLASS_BADGE: Record<string, string> = {
  private_seller: "bg-emerald-100 text-emerald-800",
  dealer: "bg-amber-100 text-amber-800",
  scam: "bg-rose-100 text-rose-800",
  uncertain: "bg-ink-100 text-ink-700",
  unclassified: "bg-ink-100 text-ink-600",
};

export function ListingsTable({ listings }: { listings: Listing[] }) {
  const [selected, setSelected] = useState<number[]>([]);

  const toggle = (id: number) => {
    setSelected((cur) =>
      cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id],
    );
  };

  const allSelected =
    listings.length > 0 && selected.length === listings.length;
  const toggleAll = () => {
    setSelected(allSelected ? [] : listings.map((l) => l.id));
  };

  return (
    <>
      <div className="panel overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="w-10 px-3 py-2.5">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  aria-label="Select all on page"
                  className="accent-brand-600"
                />
              </th>
              <th className="text-left font-medium px-4 py-2.5">Vehicle</th>
              <th className="text-left font-medium px-4 py-2.5">Location</th>
              <th className="text-right font-medium px-4 py-2.5">Mileage</th>
              <th className="text-right font-medium px-4 py-2.5">Price</th>
              <th className="text-left font-medium px-4 py-2.5">Source</th>
              <th className="text-left font-medium px-4 py-2.5">Class</th>
              <th className="text-right font-medium px-4 py-2.5">Posted</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-200">
            {listings.map((l) => {
              const vehicle =
                [l.year, l.make, l.model].filter(Boolean).join(" ") || l.title || "—";
              const loc =
                [l.city, l.state].filter(Boolean).join(", ") || l.zip_code || "—";
              const isChecked = selected.includes(l.id);
              return (
                <tr
                  key={l.id}
                  className={`${isChecked ? "bg-brand-50" : ""} hover:bg-ink-50`}
                >
                  <td className="px-3 py-3">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggle(l.id)}
                      aria-label={`Select ${vehicle}`}
                      className="accent-brand-600"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/listings/${l.id}`}
                      className="block font-medium text-ink-900 hover:text-brand-600"
                    >
                      {vehicle}
                    </Link>
                    {l.title && l.title !== vehicle && (
                      <p className="mt-0.5 truncate text-xs text-ink-500 max-w-md">
                        {l.title}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-ink-700">{loc}</td>
                  <td className="px-4 py-3 text-right tabular text-ink-700">
                    {formatMileage(l.mileage)}
                  </td>
                  <td className="px-4 py-3 text-right tabular font-semibold">
                    {formatPrice(l.price)}
                  </td>
                  <td className="px-4 py-3 text-ink-600">{l.source}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`badge ${
                        CLASS_BADGE[l.classification] ?? CLASS_BADGE.unclassified
                      }`}
                    >
                      {l.classification.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-xs text-ink-500 tabular">
                    {formatRelativeDate(l.posted_at ?? l.first_seen_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <BulkClaimBar selected={selected} onClear={() => setSelected([])} />
    </>
  );
}
