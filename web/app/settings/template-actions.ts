"use server";

import { revalidatePath } from "next/cache";

import {
  FsboApiError,
  createTemplate,
  deleteTemplate,
  updateTemplate,
} from "@/lib/api";

interface Result {
  ok: boolean;
  error?: string;
}

export async function createTemplateAction(formData: FormData): Promise<Result> {
  const name = (formData.get("name") as string)?.trim();
  const category = ((formData.get("category") as string) || "outreach").trim();
  const body = (formData.get("body") as string)?.trim();
  if (!name || !body) return { ok: false, error: "Name and body required" };
  try {
    await createTemplate(name, category, body);
    revalidatePath("/settings");
    return { ok: true };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "Create failed";
    return { ok: false, error: msg };
  }
}

export async function updateTemplateAction(formData: FormData): Promise<Result> {
  const id = Number(formData.get("id"));
  const name = (formData.get("name") as string)?.trim();
  const category = ((formData.get("category") as string) || "outreach").trim();
  const body = (formData.get("body") as string)?.trim();
  if (!Number.isFinite(id)) return { ok: false, error: "Invalid template" };
  if (!name || !body) return { ok: false, error: "Name and body required" };
  try {
    await updateTemplate(id, { name, category, body });
    revalidatePath("/settings");
    return { ok: true };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "Update failed";
    return { ok: false, error: msg };
  }
}

export async function deleteTemplateAction(formData: FormData): Promise<void> {
  const id = Number(formData.get("id"));
  if (!Number.isFinite(id)) return;
  try {
    await deleteTemplate(id);
  } catch {
    // swallow — UI re-fetches
  }
  revalidatePath("/settings");
}
