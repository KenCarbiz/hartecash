"use server";

import { revalidatePath } from "next/cache";

import { addInteraction, createLead, patchLead } from "@/lib/api";
import type { InteractionKind, LeadStatus } from "@/lib/api";

export async function claimLeadAction(formData: FormData): Promise<void> {
  const listingId = Number(formData.get("listing_id"));
  const assignedTo = (formData.get("assigned_to") as string) || undefined;
  await createLead(listingId, assignedTo);
  revalidatePath(`/listings/${listingId}`);
}

export async function updateLeadStatusAction(formData: FormData): Promise<void> {
  const leadId = Number(formData.get("lead_id"));
  const listingId = Number(formData.get("listing_id"));
  const status = formData.get("status") as LeadStatus;
  await patchLead(leadId, { status });
  revalidatePath(`/listings/${listingId}`);
}

export async function addInteractionAction(formData: FormData): Promise<void> {
  const leadId = Number(formData.get("lead_id"));
  const listingId = Number(formData.get("listing_id"));
  const kind = formData.get("kind") as InteractionKind;
  const body = (formData.get("body") as string) ?? "";
  if (!body.trim()) return;
  await addInteraction(leadId, kind, body.trim(), "outbound");
  revalidatePath(`/listings/${listingId}`);
}
