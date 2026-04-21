"use server";

import { redirect } from "next/navigation";

import { FsboApiError, createSavedSearch } from "@/lib/api";

export async function startOnboardingAction(
  formData: FormData,
): Promise<{ ok: boolean; error?: string }> {
  const zip = (formData.get("zip") as string)?.trim();
  const radius = Number(formData.get("radius_miles") || 100);
  const priceMax = Number(formData.get("price_max") || 0);
  const makes = formData.getAll("makes").map((m) => String(m));
  const alerts = formData.get("alerts_enabled") !== "off";

  if (!zip) return { ok: false, error: "ZIP required" };

  // Build a saved-search query. For multiple makes we create one per make
  // so alerts fire cleanly for each.
  const queries = makes.length > 0 ? makes : [null];
  for (const make of queries) {
    const query: Record<string, unknown> = {
      near_zip: zip,
      radius_miles: Number.isFinite(radius) && radius > 0 ? radius : 100,
      classification: "private_seller",
    };
    if (make) query.make = make;
    if (priceMax > 0) query.price_max = priceMax;
    const name = make ? `${make} near ${zip}` : `Near ${zip}`;
    try {
      await createSavedSearch(name, query, alerts);
    } catch (err) {
      const msg = err instanceof FsboApiError ? err.message : "Create failed";
      return { ok: false, error: msg };
    }
  }
  redirect("/listings");
}
