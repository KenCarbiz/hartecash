"use client";

import { useMemo, useState, useTransition } from "react";

import {
  createOfferAction,
  withdrawOfferAction,
} from "@/app/listings/[id]/offer-actions";
import { formatRelativeDate, type DealerOffer } from "@/lib/api";

interface BreakdownRow {
  label: string;
  amount: string; // "1900" or "-300" — dollars, signed
}

interface Props {
  leadId: number | null;
  listingId: number;
  appOrigin: string;
  offers: DealerOffer[];
  // Hint to seed the breakdown with a market-baseline row.
  marketMedian: number | null;
}

export function OfferComposerPanel({
  leadId,
  listingId,
  appOrigin,
  offers,
  marketMedian,
}: Props) {
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  const initialRows: BreakdownRow[] = useMemo(() => {
    if (marketMedian) {
      return [{ label: "Market baseline", amount: String(Math.round(marketMedian)) }];
    }
    return [{ label: "", amount: "" }];
  }, [marketMedian]);

  const [rows, setRows] = useState<BreakdownRow[]>(initialRows);
  const [notes, setNotes] = useState("");
  const [validHours, setValidHours] = useState(48);

  const total = rows.reduce((sum, r) => {
    const n = parseFloat(r.amount);
    return sum + (Number.isFinite(n) ? n : 0);
  }, 0);
  const totalCents = Math.round(total * 100);

  const addRow = () => setRows([...rows, { label: "", amount: "" }]);
  const removeRow = (i: number) =>
    setRows(rows.length > 1 ? rows.filter((_, idx) => idx !== i) : rows);
  const setRow = (i: number, patch: Partial<BreakdownRow>) =>
    setRows(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  const submit = () => {
    if (!leadId) {
      setError("Claim this listing as a lead first.");
      return;
    }
    if (totalCents <= 0) {
      setError("Total must be greater than $0.");
      return;
    }
    setError(null);
    startTransition(async () => {
      const breakdown = rows
        .filter((r) => r.label.trim() && r.amount.trim())
        .map((r) => ({
          label: r.label.trim(),
          amount_cents: Math.round(parseFloat(r.amount) * 100),
        }));
      const res = await createOfferAction(
        {
          lead_id: leadId,
          amount_cents: totalCents,
          breakdown,
          notes: notes.trim() || null,
          valid_hours: validHours,
        },
        listingId,
      );
      if (!res.ok) {
        setError(res.error ?? "couldn't create offer");
        return;
      }
      // Reset the composer for the next offer.
      setRows(initialRows);
      setNotes("");
      setOpen(false);
    });
  };

  const withdraw = (offerId: number) => {
    startTransition(async () => {
      const res = await withdrawOfferAction(offerId, listingId);
      if (!res.ok) setError(res.error ?? "withdraw failed");
    });
  };

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Cash offers</h3>
          <p className="text-[11px] text-ink-500 mt-0.5">
            Build + send a price-locked offer link
          </p>
        </div>
        {!open && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            disabled={!leadId || pending}
            className="btn-primary text-xs"
          >
            New offer
          </button>
        )}
      </div>

      {open && leadId && (
        <div className="space-y-3 p-4 border-b border-ink-100">
          <p className="text-[11px] text-ink-500">
            Each line is a deduction or bump in dollars. Total is what
            the seller sees as your firm offer.
          </p>

          <div className="space-y-1.5">
            {rows.map((r, idx) => (
              <div key={idx} className="flex gap-2">
                <input
                  value={r.label}
                  onChange={(e) => setRow(idx, { label: e.target.value })}
                  placeholder="e.g. 2022 Carfax accident"
                  maxLength={128}
                  className="input flex-1 text-xs"
                />
                <input
                  value={r.amount}
                  onChange={(e) => setRow(idx, { amount: e.target.value })}
                  inputMode="decimal"
                  placeholder="-300"
                  className="input w-24 text-xs font-mono tabular text-right"
                />
                <button
                  type="button"
                  onClick={() => removeRow(idx)}
                  disabled={rows.length <= 1}
                  className="text-ink-400 hover:text-rose-700 px-1 text-xs"
                  aria-label="Remove line"
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={addRow}
            className="text-xs text-brand-600 hover:text-brand-700"
          >
            + Add line
          </button>

          <div className="rounded-md border border-ink-200 bg-ink-50 px-3 py-2 flex items-center justify-between">
            <span className="text-xs uppercase tracking-wider text-ink-500">
              Offer total
            </span>
            <span className="font-semibold text-lg tabular text-ink-900">
              {formatMoney(totalCents)}
            </span>
          </div>

          <label className="block">
            <span className="text-[11px] uppercase tracking-wider text-ink-500">
              Optional note to seller
            </span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              maxLength={1000}
              placeholder="e.g. We'll come to you. Cashier's check on the spot."
              className="input mt-1 text-xs"
            />
          </label>

          <label className="flex items-center gap-2 text-xs">
            <span className="text-[11px] uppercase tracking-wider text-ink-500">
              Lock for
            </span>
            <select
              value={validHours}
              onChange={(e) => setValidHours(Number(e.target.value))}
              className="input w-auto text-xs"
            >
              <option value={24}>24 hours</option>
              <option value={48}>48 hours</option>
              <option value={72}>3 days</option>
              <option value={168}>7 days</option>
            </select>
          </label>

          {error && (
            <p className="text-xs text-rose-700">⚠ {error}</p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={submit}
              disabled={pending || totalCents <= 0}
              className="btn-primary text-xs"
            >
              {pending ? "Creating…" : "Send offer link"}
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={pending}
              className="btn-secondary text-xs"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {offers.length === 0 ? (
        <p className="px-5 py-4 text-xs text-ink-500">
          No offers sent yet. Click <strong>New offer</strong> to build one
          and text the link to the seller.
        </p>
      ) : (
        <ul className="divide-y divide-ink-100">
          {offers.map((o) => (
            <OfferRow
              key={o.id}
              offer={o}
              appOrigin={appOrigin}
              onWithdraw={() => withdraw(o.id)}
              pending={pending}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

const STATUS_TONE: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800",
  accepted: "bg-emerald-100 text-emerald-800",
  declined: "bg-rose-100 text-rose-800",
  withdrawn: "bg-ink-100 text-ink-700",
  expired: "bg-ink-200 text-ink-700",
};

function OfferRow({
  offer,
  appOrigin,
  onWithdraw,
  pending,
}: {
  offer: DealerOffer;
  appOrigin: string;
  onWithdraw: () => void;
  pending: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const url = `${appOrigin}/o/${offer.public_token}`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Manual select fallback — no-op
    }
  };

  return (
    <li className="px-5 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <span className="text-base font-semibold tabular text-ink-900">
            {formatMoney(offer.amount_cents)}
          </span>
          <span
            className={`ml-2 inline-block rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${
              STATUS_TONE[offer.status] ?? "bg-ink-100 text-ink-700"
            }`}
          >
            {offer.status}
          </span>
        </div>
        <time className="text-[11px] tabular text-ink-500">
          {formatRelativeDate(offer.created_at)}
        </time>
      </div>

      {offer.notes && (
        <p className="mt-1 text-[11px] text-ink-600 line-clamp-2">
          {offer.notes}
        </p>
      )}

      {offer.seller_viewed_at && (
        <p className="mt-1 text-[11px] text-ink-500">
          Seller opened {formatRelativeDate(offer.seller_viewed_at)}
        </p>
      )}
      {offer.seller_response_note && (
        <p className="mt-1 rounded-md border border-ink-200 bg-ink-50 px-2 py-1 text-[11px] text-ink-700">
          “{offer.seller_response_note}”
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <code className="rounded bg-ink-50 border border-ink-200 px-2 py-1 text-[11px] text-ink-700 truncate max-w-[200px]">
          {url}
        </code>
        <button
          type="button"
          onClick={copy}
          className="btn-secondary text-[11px] py-1"
        >
          {copied ? "✓ Copied" : "Copy link"}
        </button>
        {offer.status === "pending" && (
          <button
            type="button"
            onClick={onWithdraw}
            disabled={pending}
            className="text-[11px] text-rose-700 hover:text-rose-800 ml-auto"
          >
            Withdraw
          </button>
        )}
      </div>
    </li>
  );
}

function formatMoney(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}
