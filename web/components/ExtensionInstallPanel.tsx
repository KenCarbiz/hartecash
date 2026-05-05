"use client";

import { useEffect, useState, useTransition } from "react";

import { issueExtensionInstallCodeAction } from "@/app/settings/install-code-action";

interface IssuedCode {
  code: string;
  expires_at: string;
  expires_in_seconds: number;
}

/** Onboarding helper for the AutoAcquisition Chrome extension.
 *
 *  Click the button → server mints an 8-char install code (single-use,
 *  10-min TTL). Dealer pastes the code into the extension popup, which
 *  exchanges it for a fresh API key. The full secret never appears in
 *  the dealer's clipboard. */
export function ExtensionInstallPanel() {
  const [issued, setIssued] = useState<IssuedCode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!issued) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [issued]);

  const remaining = issued
    ? Math.max(
        0,
        Math.floor((new Date(issued.expires_at).getTime() - now) / 1000),
      )
    : 0;
  const expired = issued && remaining === 0;

  const issue = () => {
    setError(null);
    setCopied(false);
    startTransition(async () => {
      const res = await issueExtensionInstallCodeAction();
      if ("error" in res) {
        setError(res.error);
      } else {
        setIssued(res);
        setNow(Date.now());
      }
    });
  };

  const copy = async () => {
    if (!issued) return;
    try {
      await navigator.clipboard.writeText(issued.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Couldn't copy — select the code manually.");
    }
  };

  return (
    <div className="panel p-5">
      <h2 className="text-sm font-semibold">Connect the Chrome extension</h2>
      <p className="mt-0.5 text-xs text-ink-500">
        Generate a one-time code, then paste it into the AutoAcquisition
        extension popup. The extension exchanges the code for a fresh
        API key — you never copy the full secret.
      </p>

      {!issued && (
        <button
          type="button"
          onClick={issue}
          disabled={pending}
          className="btn-primary mt-3 text-xs"
        >
          {pending ? "Generating…" : "Generate install code"}
        </button>
      )}

      {issued && (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-3 rounded-md border border-ink-200 bg-ink-50 px-4 py-3">
            <code
              className={`font-mono text-2xl tracking-[0.3em] tabular ${
                expired ? "line-through text-ink-400" : "text-ink-900"
              }`}
            >
              {issued.code}
            </code>
            <div className="ml-auto flex items-center gap-2">
              <span
                className={`text-[11px] tabular ${
                  expired ? "text-rose-700" : "text-ink-500"
                }`}
              >
                {expired
                  ? "Expired"
                  : `Expires in ${formatRemaining(remaining)}`}
              </span>
              {!expired && (
                <button
                  type="button"
                  onClick={copy}
                  className="btn-secondary text-xs"
                >
                  {copied ? "✓ Copied" : "Copy"}
                </button>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={issue}
            disabled={pending}
            className="text-xs text-brand-600 hover:text-brand-700"
          >
            Generate a new code
          </button>
        </div>
      )}

      {error && (
        <p className="mt-3 text-xs text-rose-700">⚠ {error}</p>
      )}
    </div>
  );
}

function formatRemaining(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
