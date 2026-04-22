"use server";

import { revalidatePath } from "next/cache";

import { FsboApiError, patchListingFacts } from "@/lib/api";

export async function patchFactsAction(
  formData: FormData,
): Promise<{ ok: boolean; error?: string }> {
  const id = Number(formData.get("listing_id"));
  if (!Number.isFinite(id)) return { ok: false, error: "invalid listing" };

  const patch: Parameters<typeof patchListingFacts>[1] = {};
  for (const key of [
    "license_plate",
    "license_plate_state",
    "color",
    "vin",
  ] as const) {
    const raw = formData.get(key);
    if (raw !== null) {
      patch[key] = typeof raw === "string" ? raw : "";
    }
  }

  // Drivable is a tri-state radio: "yes" / "no" / "unknown". Only send
  // the field when an explicit choice was made (form always includes it
  // here, but we tolerate its absence).
  const driv = formData.get("drivable");
  if (driv === "yes") patch.drivable = true;
  else if (driv === "no") patch.drivable = false;
  else if (driv === "unknown") patch.drivable = null;

  try {
    await patchListingFacts(id, patch);
    revalidatePath(`/listings/${id}`);
    return { ok: true };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "save failed";
    return { ok: false, error: msg };
  }
}
