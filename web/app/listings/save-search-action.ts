"use server";

import { revalidatePath } from "next/cache";

import { createSavedSearch, deleteSavedSearch } from "@/lib/api";

export async function saveCurrentSearch(formData: FormData): Promise<void> {
  const name = (formData.get("name") as string)?.trim();
  if (!name) return;
  const queryJson = (formData.get("query") as string) ?? "{}";
  const alerts = formData.get("alerts_enabled") === "on";
  try {
    const parsed = JSON.parse(queryJson) as Record<string, unknown>;
    await createSavedSearch(name, parsed, alerts);
  } catch {
    // Silent fail — invalid JSON shouldn't crash the form post. Server
    // validation will surface real errors.
  }
  revalidatePath("/listings");
}

export async function deleteSavedSearchAction(formData: FormData): Promise<void> {
  const id = Number(formData.get("id"));
  if (!Number.isFinite(id)) return;
  await deleteSavedSearch(id);
  revalidatePath("/listings");
}
