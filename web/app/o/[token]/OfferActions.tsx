"use client";

import { useState, useTransition } from "react";

import {
  acceptOfferAction,
  declineOfferAction,
} from "@/app/o/[token]/actions";

export function OfferActions({ token }: { token: string }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [confirmingDecline, setConfirmingDecline] = useState(false);

  const accept = () => {
    setError(null);
    startTransition(async () => {
      const res = await acceptOfferAction(token, note.trim());
      if (!res.ok) setError(res.error ?? "couldn't accept");
    });
  };

  const decline = () => {
    setError(null);
    startTransition(async () => {
      const res = await declineOfferAction(token, note.trim());
      if (!res.ok) setError(res.error ?? "couldn't decline");
    });
  };

  return (
    <div className="space-y-3">
      <label className="block">
        <span className="text-xs uppercase tracking-wider text-ink-500">
          Optional note to the buyer
        </span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          maxLength={1000}
          placeholder="e.g. I can meet at 3pm tomorrow"
          className="input mt-1"
        />
      </label>

      {error && (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <button
          type="button"
          onClick={accept}
          disabled={pending}
          className="btn-primary flex-1 justify-center text-base py-2.5"
        >
          {pending ? "Submitting…" : "Accept this offer"}
        </button>
        {!confirmingDecline ? (
          <button
            type="button"
            onClick={() => setConfirmingDecline(true)}
            disabled={pending}
            className="btn-secondary flex-1 justify-center text-base py-2.5"
          >
            Decline
          </button>
        ) : (
          <button
            type="button"
            onClick={decline}
            disabled={pending}
            className="btn-secondary flex-1 justify-center text-base py-2.5 border-rose-300 text-rose-800 bg-rose-50 hover:bg-rose-100"
          >
            {pending ? "Submitting…" : "Confirm decline"}
          </button>
        )}
      </div>
    </div>
  );
}
