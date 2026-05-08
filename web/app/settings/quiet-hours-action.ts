"use server";

import { revalidatePath } from "next/cache";

import { FsboApiError, updateQuietHours } from "@/lib/api";

export async function updateQuietHoursAction(
  formData: FormData,
): Promise<{ ok: boolean; error?: string }> {
  const action = (formData.get("action") as string) || "save";
  if (action === "reset") {
    try {
      await updateQuietHours(null, null);
      revalidatePath("/settings");
      return { ok: true };
    } catch (err) {
      return {
        ok: false,
        error: err instanceof FsboApiError ? err.message : "Reset failed",
      };
    }
  }

  const start = ((formData.get("start") as string) || "").trim() || null;
  const end = ((formData.get("end") as string) || "").trim() || null;
  try {
    await updateQuietHours(start, end);
    revalidatePath("/settings");
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof FsboApiError ? err.message : "Save failed",
    };
  }
}
