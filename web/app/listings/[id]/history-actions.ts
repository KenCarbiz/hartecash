"use server";

import { revalidatePath } from "next/cache";

import { FsboApiError, refreshHistoryReport } from "@/lib/api";

export async function refreshHistoryReportAction(
  listingId: number,
): Promise<{ ok: boolean; error?: string }> {
  try {
    await refreshHistoryReport(listingId);
    revalidatePath(`/listings/${listingId}`);
    return { ok: true };
  } catch (err) {
    let message = "Couldn't refresh history report";
    if (err instanceof FsboApiError) {
      message = err.body || err.message;
      if (err.status === 400) message = "No VIN on this listing";
    }
    return { ok: false, error: message };
  }
}
