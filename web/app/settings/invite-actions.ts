"use server";

import { revalidatePath } from "next/cache";

import {
  FsboApiError,
  createInvitation,
  revokeInvitation,
} from "@/lib/api";

export async function createInviteAction(
  formData: FormData,
): Promise<{ token: string | null; error: string | null; url: string | null }> {
  const email = (formData.get("email") as string)?.trim();
  const role = (formData.get("role") as string) || "member";
  if (!email) return { token: null, error: "Email required", url: null };
  try {
    const invite = await createInvitation(email, role);
    revalidatePath("/settings");
    return {
      token: invite.token,
      error: null,
      url: invite.accept_url_hint,
    };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "Invite failed";
    return { token: null, error: msg, url: null };
  }
}

export async function revokeInviteAction(formData: FormData): Promise<void> {
  const id = Number(formData.get("id"));
  if (!Number.isFinite(id)) return;
  try {
    await revokeInvitation(id);
  } catch {
    // swallow
  }
  revalidatePath("/settings");
}
