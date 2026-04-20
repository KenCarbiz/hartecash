"use server";

import { revalidatePath } from "next/cache";

import {
  addInteraction,
  aiOpener,
  bumpActivity,
  FsboApiError,
  renderTemplate,
} from "@/lib/api";

export async function composeOpenerAction(
  listingId: number,
  tone: "direct" | "friendly" | "cash-buyer",
): Promise<{ message: string } | { error: string }> {
  try {
    const resp = await aiOpener(listingId, tone);
    return { message: resp.message };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "AI opener failed";
    return { error: msg };
  }
}

export async function renderTemplateAction(
  templateId: number,
  listingId: number,
): Promise<{ rendered: string } | { error: string }> {
  try {
    const resp = await renderTemplate(templateId, listingId);
    return { rendered: resp.rendered };
  } catch (err) {
    const msg = err instanceof FsboApiError ? err.message : "Template render failed";
    return { error: msg };
  }
}

export async function logSentMessageAction(
  leadId: number,
  listingId: number,
  body: string,
  source: string,
): Promise<void> {
  await addInteraction(leadId, "text", body, "outbound");
  await bumpActivity({ messages_sent: 1 }).catch(() => {});
  void source;
  revalidatePath(`/listings/${listingId}`);
}
