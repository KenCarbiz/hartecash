"use server";

import { revalidatePath } from "next/cache";

import {
  type DealerOffer,
  FsboApiError,
  createOffer,
  withdrawOffer,
} from "@/lib/api";

export interface CreateOfferInput {
  lead_id: number;
  amount_cents: number;
  breakdown: { label: string; amount_cents: number }[];
  notes: string | null;
  valid_hours: number;
}

export async function createOfferAction(
  input: CreateOfferInput,
  listingId: number,
): Promise<{ ok: boolean; offer?: DealerOffer; error?: string }> {
  try {
    const offer = await createOffer(input);
    revalidatePath(`/listings/${listingId}`);
    return { ok: true, offer };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof FsboApiError ? err.message : "couldn't create offer",
    };
  }
}

export async function withdrawOfferAction(
  offerId: number,
  listingId: number,
): Promise<{ ok: boolean; error?: string }> {
  try {
    await withdrawOffer(offerId);
    revalidatePath(`/listings/${listingId}`);
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof FsboApiError ? err.message : "withdraw failed",
    };
  }
}
