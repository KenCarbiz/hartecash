"use server";

import { revalidatePath } from "next/cache";

import { FsboApiError, importLeadsCsv, type ImportResult } from "@/lib/api";

export async function importLeadsAction(
  formData: FormData,
): Promise<{ ok: boolean; result?: ImportResult; error?: string }> {
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return { ok: false, error: "Pick a CSV file first" };
  }
  if (file.size > 5_000_000) {
    return { ok: false, error: "CSV is too large (5 MB max)" };
  }
  try {
    const result = await importLeadsCsv(file);
    revalidatePath("/leads");
    revalidatePath("/settings");
    return { ok: true, result };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "Import failed";
    return { ok: false, error: msg };
  }
}
