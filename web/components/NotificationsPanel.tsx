"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { updateNotificationPrefsAction } from "@/app/settings/notification-actions";
import type { NotificationPreferences } from "@/lib/api";

export function NotificationsPanel({
  prefs,
}: {
  prefs: NotificationPreferences;
}) {
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const submit = (fd: FormData) => {
    setStatus("idle");
    setMsg(null);
    startTransition(async () => {
      const res = await updateNotificationPrefsAction(fd);
      if (res.ok) {
        setStatus("saved");
        router.refresh();
        setTimeout(() => setStatus("idle"), 1500);
      } else {
        setStatus("error");
        setMsg(res.error ?? "Update failed");
      }
    });
  };

  return (
    <div className="panel p-5">
      <h2 className="text-sm font-semibold">Email alerts</h2>
      <p className="text-[11px] text-ink-500 mt-0.5">
        Get notified when a new listing matches one of your saved searches
        AND scores above your threshold.
      </p>

      <form action={submit} className="mt-4 space-y-4">
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            name="alerts_enabled"
            defaultChecked={prefs.alerts_enabled}
            className="accent-brand-600 h-4 w-4"
          />
          <span className="text-sm">Send me email alerts</span>
        </label>

        <label className="block max-w-xs">
          <span className="label">Minimum lead score</span>
          <input
            type="number"
            name="alert_min_score"
            min={0}
            max={100}
            defaultValue={prefs.alert_min_score}
            className="input mt-1"
          />
          <p className="mt-1 text-[11px] text-ink-500">
            80 = Hot only (recommended). Lower = more alerts, more noise.
          </p>
        </label>

        <div className="flex items-center gap-3">
          <button type="submit" disabled={pending} className="btn-primary">
            {pending ? "Saving…" : "Save"}
          </button>
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
