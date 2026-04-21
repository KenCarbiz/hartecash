"use server";

import { revalidatePath } from "next/cache";

import { FsboApiError, patchLead } from "@/lib/api";

export async function reassignLeadAction(
  formData: FormData,
): Promise<{ ok: boolean; error?: string }> {
  const id = Number(formData.get("lead_id"));
  const assignedRaw = formData.get("assigned_to");
  const assigned = typeof assignedRaw === "string" ? assignedRaw : "";
  if (!Number.isFinite(id)) return { ok: false, error: "invalid lead" };
  try {
    await patchLead(id, { assigned_to: assigned || null });
    revalidatePath("/leads");
    revalidatePath(`/listings`);
    return { ok: true };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "reassign failed";
    return { ok: false, error: msg };
  }
}
