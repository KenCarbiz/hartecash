"use server";

import { revalidatePath } from "next/cache";

import {
  FsboApiError,
  updateNotificationPrefs,
} from "@/lib/api";

export async function updateNotificationPrefsAction(
  formData: FormData,
): Promise<{ ok: boolean; error?: string }> {
  const alertsEnabled = formData.get("alerts_enabled") === "on";
  const rawScore = formData.get("alert_min_score") as string | null;
  const score = rawScore ? Number(rawScore) : undefined;
  const rawPhone = formData.get("phone") as string | null;
  try {
    await updateNotificationPrefs({
      alerts_enabled: alertsEnabled,
      alert_min_score:
        score !== undefined && Number.isFinite(score) ? score : undefined,
      // Empty string clears the phone server-side (handled in the API).
      phone: rawPhone !== null ? rawPhone : undefined,
    });
    revalidatePath("/settings");
    return { ok: true };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "Update failed";
    return { ok: false, error: msg };
  }
}
