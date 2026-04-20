"use server";

import { revalidatePath } from "next/cache";

import { createApiKey, FsboApiError, revokeApiKey } from "@/lib/api";

export async function createApiKeyAction(
  formData: FormData,
): Promise<{ token: string | null; error: string | null; prefix: string | null }> {
  const name = (formData.get("name") as string)?.trim();
  if (!name) return { token: null, error: "Name required", prefix: null };
  try {
    const key = await createApiKey(name);
    revalidatePath("/settings");
    return { token: key.token, error: null, prefix: key.token_prefix };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "Create failed";
    return { token: null, error: msg, prefix: null };
  }
}

export async function revokeApiKeyAction(formData: FormData): Promise<void> {
  const id = Number(formData.get("id"));
  if (!Number.isFinite(id)) return;
  try {
    await revokeApiKey(id);
  } catch {
    // swallow — UI will re-fetch and show current state
  }
  revalidatePath("/settings");
}
