"use server";

import { revalidatePath } from "next/cache";

import { FsboApiError, startVoiceCall } from "@/lib/api";

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
