"use server";

import { revalidatePath } from "next/cache";

import {
  FsboApiError,
  bulkLeadArchive,
  bulkLeadAssign,
  bulkLeadStatus,
  type LeadStatus,
} from "@/lib/api";

type ActionResult = {
  ok: boolean;
  updated?: number;
  skipped?: number;
  error?: string;
};

function _err(err: unknown): ActionResult {
  const msg = err instanceof FsboApiError ? err.message : "Action failed";
  return { ok: false, error: msg };
}

export async function bulkStatusAction(
  leadIds: number[],
  status: LeadStatus,
): Promise<ActionResult> {
  if (leadIds.length === 0) return { ok: false, error: "No leads selected" };
  try {
    const res = await bulkLeadStatus(leadIds, status);
    revalidatePath("/leads");
    return { ok: true, updated: res.updated, skipped: res.skipped };
  } catch (err) {
    return _err(err);
  }
}

export async function bulkAssignAction(
  leadIds: number[],
  assignedTo: string | null,
): Promise<ActionResult> {
  if (leadIds.length === 0) return { ok: false, error: "No leads selected" };
  try {
    const res = await bulkLeadAssign(leadIds, assignedTo);
    revalidatePath("/leads");
    return { ok: true, updated: res.updated, skipped: res.skipped };
  } catch (err) {
    return _err(err);
  }
}

export async function bulkArchiveAction(
  leadIds: number[],
  reason?: string,
): Promise<ActionResult> {
  if (leadIds.length === 0) return { ok: false, error: "No leads selected" };
  try {
    const res = await bulkLeadArchive(leadIds, reason);
    revalidatePath("/leads");
    return { ok: true, updated: res.updated, skipped: res.skipped };
  } catch (err) {
    return _err(err);
  }
}
