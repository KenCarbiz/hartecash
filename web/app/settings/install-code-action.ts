"use server";

import {
  FsboApiError,
  issueExtensionInstallCode,
  type ExtensionInstallCode,
} from "@/lib/api";

export async function issueExtensionInstallCodeAction(): Promise<
  ExtensionInstallCode | { error: string }
> {
  try {
    return await issueExtensionInstallCode();
  } catch (err) {
    if (err instanceof FsboApiError) {
      return { error: err.message };
    }
    return { error: "Couldn't generate code" };
  }
}
