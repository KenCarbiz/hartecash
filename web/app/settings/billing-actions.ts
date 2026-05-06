"use server";

import { redirect } from "next/navigation";

import {
  FsboApiError,
  openBillingPortal,
  startCheckout,
} from "@/lib/api";

function originFromHeaders(host: string, proto: string): string {
  return `${proto}://${host}`;
}

export async function startCheckoutAction(
  plan: "starter" | "pro" | "performance",
  origin: string,
): Promise<{ ok: boolean; error?: string }> {
  let url: string;
  try {
    url = await startCheckout(
      plan,
      `${origin}/settings?checkout=success`,
      `${origin}/settings?checkout=cancel`,
    );
  } catch (err) {
    return {
      ok: false,
      error: err instanceof FsboApiError ? err.message : "Couldn't start checkout",
    };
  }
  redirect(url);
}

export async function openBillingPortalAction(
  origin: string,
): Promise<{ ok: boolean; error?: string }> {
  let url: string;
  try {
    url = await openBillingPortal(`${origin}/settings`);
  } catch (err) {
    return {
      ok: false,
      error: err instanceof FsboApiError ? err.message : "Portal unavailable",
    };
  }
  redirect(url);
}

export { originFromHeaders };
