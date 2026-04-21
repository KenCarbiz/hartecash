"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const BASE_URL = process.env.FSBO_API_URL ?? "http://localhost:8000";
const SESSION_COOKIE = "autocurb_session";

interface AuthResult {
  ok: boolean;
  error?: string;
}

async function forwardSetCookie(res: Response): Promise<void> {
  const setCookie = res.headers.get("set-cookie");
  if (!setCookie) return;
  // Parse the Set-Cookie header and re-set it on the Next.js response cookies.
  // We keep it simple: find name=value and forward standard flags.
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

export async function loginAction(formData: FormData): Promise<AuthResult> {
  const email = (formData.get("email") as string)?.trim();
  const password = formData.get("password") as string;
  if (!email || !password) return { ok: false, error: "Email and password required" };

  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return { ok: false, error: body.detail || "Login failed" };
  }
  await forwardSetCookie(res);
  redirect("/");
}

export async function registerAction(formData: FormData): Promise<AuthResult> {
  const email = (formData.get("email") as string)?.trim();
  const password = formData.get("password") as string;
  const name = (formData.get("name") as string)?.trim() || null;
  const dealer_name = (formData.get("dealer_name") as string)?.trim() || null;

  if (!email || !password) return { ok: false, error: "Email and password required" };
  if (password.length < 8)
    return { ok: false, error: "Password must be at least 8 characters" };

  const res = await fetch(`${BASE_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name, dealer_name }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return { ok: false, error: body.detail || "Registration failed" };
  }
  await forwardSetCookie(res);
  redirect("/");
}

export async function logoutAction(): Promise<void> {
  // Best-effort: tell the backend to clear its cookie (our JWTs are
  // stateless so this mostly serves to match Max-Age=0 semantics).
  await fetch(`${BASE_URL}/auth/logout`, { method: "POST" }).catch(() => {});
  const store = await cookies();
  store.delete(SESSION_COOKIE);
  redirect("/login");
}
