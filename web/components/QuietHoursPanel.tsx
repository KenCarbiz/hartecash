"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { updateQuietHoursAction } from "@/app/settings/quiet-hours-action";
import type { QuietHours } from "@/lib/api";

export function QuietHoursPanel({ quietHours }: { quietHours: QuietHours }) {
  const [pending, startTransition] = useTransition();
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");
  const [msg, setMsg] = useState<string | null>(null);
  const router = useRouter();

  const submit = (fd: FormData) => {
    setStatus("idle");
    setMsg(null);
    startTransition(async () => {
      const res = await updateQuietHoursAction(fd);
      if (res.ok) {
        setStatus("saved");
        router.refresh();
        setTimeout(() => setStatus("idle"), 1500);
      } else {
        setStatus("error");
        setMsg(res.error ?? "Save failed");
      }
    });
  };

  return (
    <div className="panel p-5">
      <h2 className="text-sm font-semibold">Outreach quiet hours</h2>
      <p className="text-[11px] text-ink-500 mt-0.5">
        Federal TCPA bans calls before 8 AM / after 9 PM seller-local. We
        default to 8 AM - 8 PM (one hour stricter on the late side).
        Tighten further here if your dealership wants daytime-only
        outreach. You can&apos;t loosen past federal — the gate clamps
        the window so a misconfig can&apos;t expose you to a TCPA suit.
      </p>

      <form action={submit} className="mt-4 grid grid-cols-2 gap-3 max-w-sm">
        <label className="block">
          <span className="label">Start</span>
          <input
            type="time"
            name="start"
            min="08:00"
            max="20:00"
            defaultValue={quietHours.start}
            className="input mt-1"
          />
        </label>
        <label className="block">
          <span className="label">End</span>
          <input
            type="time"
            name="end"
            min="08:00"
            max="20:00"
            defaultValue={quietHours.end}
            className="input mt-1"
          />
        </label>

        <div className="col-span-2 flex items-center gap-3">
          <button type="submit" disabled={pending} className="btn-primary">
            {pending ? "Saving…" : "Save"}
          </button>
          {quietHours.is_override && (
            <button
              type="submit"
              name="action"
              value="reset"
              disabled={pending}
              className="btn-ghost text-xs"
            >
              Reset to default (8-8)
            </button>
          )}
          {status === "saved" && (
            <span className="text-xs text-emerald-600">✓ Saved</span>
          )}
          {status === "error" && (
            <span className="text-xs text-rose-600">⚠ {msg}</span>
          )}
        </div>
      </form>
    </div>
  );
}
