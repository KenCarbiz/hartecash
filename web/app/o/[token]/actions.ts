"use server";

import { revalidatePath } from "next/cache";

import {
  FsboApiError,
  publicAcceptOffer,
  publicDeclineOffer,
} from "@/lib/api";

export async function acceptOfferAction(
  token: string,
  note: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    await publicAcceptOffer(token, note || null);
    revalidatePath(`/o/${token}`);
    return { ok: true };
  } catch (err) {
    let message = "Couldn't accept";
    if (err instanceof FsboApiError) {
      message =
        err.status === 410
          ? "This offer has expired."
          : err.status === 409
          ? "This offer can no longer be accepted."
          : err.body || err.message;
    }
    return { ok: false, error: message };
  }
}

export async function declineOfferAction(
  token: string,
  note: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    await publicDeclineOffer(token, note || null);
    revalidatePath(`/o/${token}`);
    return { ok: true };
  } catch (err) {
    let message = "Couldn't decline";
    if (err instanceof FsboApiError) {
      message =
        err.status === 410
          ? "This offer has expired."
          : err.status === 409
          ? "This offer was already responded to."
          : err.body || err.message;
    }
    return { ok: false, error: message };
  }
}
