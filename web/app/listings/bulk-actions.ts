"use server";

import { revalidatePath } from "next/cache";

import { bulkClaim, FsboApiError } from "@/lib/api";

export async function bulkClaimAction(
  listingIds: number[],
  assignedTo?: string,
): Promise<
  | { claimed: number; already_claimed: number; missing_listings: number[] }
  | { error: string }
> {
  try {
    const result = await bulkClaim(listingIds, assignedTo);
    revalidatePath("/listings");
    revalidatePath("/leads");
    return result;
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "Bulk claim failed";
    return { error: msg };
  }
}
