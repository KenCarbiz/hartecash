"use client";

import { useState, useTransition } from "react";

interface ActionFn {
  (formData: FormData): Promise<{ ok: boolean; error?: string }>;
}

export function ForgotPasswordForm({ action }: { action: ActionFn }) {
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const submit = (fd: FormData) => {
    setError(null);
    startTransition(async () => {
      const res = await action(fd);
      if (!res.ok && res.error) setError(res.error);
      else setSubmitted(true);
    });
  };

  if (submitted) {
    return (
      <div className="mt-5 rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
        If there&apos;s an account with that email, we&apos;ve sent a reset
        link. Check your inbox in the next minute.
      </div>
    );
  }

  return (
    <form action={submit} className="mt-5 space-y-3">
      <label className="block">
        <span className="label">Email</span>
        <input
          name="email"
          type="email"
          required
          autoComplete="email"
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
        {pending ? "Sending…" : "Send reset link"}
      </button>
    </form>
  );
}
