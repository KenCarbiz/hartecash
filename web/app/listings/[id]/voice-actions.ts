"use server";

import { revalidatePath } from "next/cache";

import { FsboApiError, startBridgeCall, startVoiceCall } from "@/lib/api";

export async function startVoiceCallAction(
  leadId: number,
  listingId: number,
): Promise<{ ok: boolean; call_id?: number; status?: string; error?: string }> {
  try {
    const res = await startVoiceCall(leadId);
    revalidatePath(`/listings/${listingId}`);
    return { ok: true, call_id: res.call_id, status: res.status };
  } catch (err) {
    let message = "Couldn't start call";
    if (err instanceof FsboApiError) {
      message = err.message;
      // 451 = TCPA-blocked; surface a more useful hint
      if (err.status === 451) message = `Blocked by TCPA gate (${err.body || err.message})`;
      if (err.status === 400) message = "No phone number on this listing";
    }
    return { ok: false, error: message };
  }
}

export async function startBridgeCallAction(
  leadId: number,
  listingId: number,
  formData: FormData,
): Promise<{ ok: boolean; call_id?: number; status?: string; error?: string }> {
  const repPhone = ((formData.get("rep_phone") as string) || "").trim();
  if (!repPhone) {
    return { ok: false, error: "Enter your phone number" };
  }
  try {
    const res = await startBridgeCall(leadId, repPhone);
    revalidatePath(`/listings/${listingId}`);
    return { ok: true, call_id: res.call_id, status: res.status };
  } catch (err) {
    let message = "Couldn't start bridge call";
    if (err instanceof FsboApiError) {
      message = err.message;
      if (err.status === 451) message = `Blocked by TCPA gate (${err.body || err.message})`;
      if (err.status === 400) message = "Missing seller phone or rep phone";
      if (err.status === 404) message = "Lead not found";
    }
    return { ok: false, error: message };
  }
}
