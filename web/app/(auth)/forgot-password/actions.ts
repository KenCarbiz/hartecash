"use server";

const BASE_URL = process.env.FSBO_API_URL ?? "http://localhost:8000";

interface Result {
  ok: boolean;
  error?: string;
}

export async function forgotPasswordAction(formData: FormData): Promise<Result> {
  const email = (formData.get("email") as string)?.trim();
  if (!email) return { ok: false, error: "Email required" };
  try {
    await fetch(`${BASE_URL}/auth/forgot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    // Always return OK so the UI doesn't leak whether the email exists.
    return { ok: true };
  } catch {
    return { ok: false, error: "Couldn't reach the server" };
  }
}
