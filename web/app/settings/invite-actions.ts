"use server";

import { revalidatePath } from "next/cache";

import {
  FsboApiError,
  createInvitation,
  getCurrentUser,
  revokeInvitation,
} from "@/lib/api";

/** Defense-in-depth role gate. The settings page hides the
 *  InvitationsPanel for non-admin users, but the server actions
 *  themselves should refuse non-admin callers — a malicious client
 *  could call the action directly without rendering the page. The
 *  backend route also enforces this; this is the second line of
 *  defense per the audit.
 */
async function _requireAdmin(): Promise<{ ok: true } | { ok: false; error: string }> {
  const user = await getCurrentUser().catch(() => null);
  if (!user) return { ok: false, error: "Not signed in" };
  if (user.role !== "admin") return { ok: false, error: "Admin role required" };
  return { ok: true };
}

export async function createInviteAction(
  formData: FormData,
): Promise<{ token: string | null; error: string | null; url: string | null }> {
  const guard = await _requireAdmin();
  if (!guard.ok) return { token: null, error: guard.error, url: null };
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
  const guard = await _requireAdmin();
  if (!guard.ok) return;
  const id = Number(formData.get("id"));
  if (!Number.isFinite(id)) return;
  try {
    await revokeInvitation(id);
  } catch {
    // swallow
  }
  revalidatePath("/settings");
}
