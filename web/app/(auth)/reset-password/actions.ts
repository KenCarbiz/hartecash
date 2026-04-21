"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const BASE_URL = process.env.FSBO_API_URL ?? "http://localhost:8000";
const SESSION_COOKIE = "autocurb_session";

interface Result {
  ok: boolean;
  error?: string;
}

async function forwardSetCookie(res: Response): Promise<void> {
  const setCookie = res.headers.get("set-cookie");
  if (!setCookie) return;
  const parts = setCookie.split(";").map((p) => p.trim());
  const [nameValue, ...flags] = parts;
  const eq = nameValue.indexOf("=");
  if (eq === -1) return;
  const name = nameValue.slice(0, eq);
  const value = nameValue.slice(eq + 1);
  if (name !== SESSION_COOKIE) return;
  const opts: Parameters<Awaited<ReturnType<typeof cookies>>["set"]>[2] = {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure: process.env.NODE_ENV === "production",
  };
  for (const flag of flags) {
    const lower = flag.toLowerCase();
    if (lower.startsWith("max-age=")) {
      opts.maxAge = Number(flag.slice(8)) || undefined;
    } else if (lower.startsWith("path=")) {
      opts.path = flag.slice(5);
    } else if (lower.startsWith("domain=")) {
      opts.domain = flag.slice(7);
    }
  }
  const store = await cookies();
  store.set(SESSION_COOKIE, value, opts);
}

export async function resetPasswordAction(formData: FormData): Promise<Result> {
  const token = (formData.get("token") as string)?.trim();
  const password = formData.get("password") as string;
  if (!token) return { ok: false, error: "Missing reset token" };
  if (!password || password.length < 8)
    return { ok: false, error: "Password must be at least 8 characters" };

  const res = await fetch(`${BASE_URL}/auth/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return { ok: false, error: body.detail || "Reset failed" };
  }
  await forwardSetCookie(res);
  redirect("/");
}
