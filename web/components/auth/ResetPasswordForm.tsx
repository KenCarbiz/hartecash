"use client";

import { useState, useTransition } from "react";

interface ActionFn {
  (formData: FormData): Promise<{ ok: boolean; error?: string }>;
}

export function ResetPasswordForm({
  action,
  token,
}: {
  action: ActionFn;
  token: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const submit = (fd: FormData) => {
    setError(null);
    startTransition(async () => {
      const res = await action(fd);
      if (!res.ok && res.error) setError(res.error);
    });
  };

  return (
    <form action={submit} className="mt-5 space-y-3">
      <input type="hidden" name="token" value={token} />
      <label className="block">
        <span className="label">New password</span>
        <input
          name="password"
          type="password"
          minLength={8}
          required
          autoComplete="new-password"
          className="input mt-1"
        />
      </label>
      {error && (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="btn-primary w-full justify-center"
      >
        {pending ? "Resetting…" : "Reset password & sign in"}
      </button>
    </form>
  );
}
