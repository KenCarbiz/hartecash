"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import {
  createApiKeyAction,
  revokeApiKeyAction,
} from "@/app/settings/actions";
import type { ApiKeyRow } from "@/lib/api";
import { formatRelativeDate } from "@/lib/api";

export function ApiKeysPanel({ keys }: { keys: ApiKeyRow[] }) {
  const [newToken, setNewToken] = useState<string | null>(null);
  const [tokenPrefix, setTokenPrefix] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const onCreate = (fd: FormData) => {
    startTransition(async () => {
      const res = await createApiKeyAction(fd);
      if (res.error) {
        setError(res.error);
        setNewToken(null);
      } else {
        setError(null);
        setNewToken(res.token);
        setTokenPrefix(res.prefix);
      }
      router.refresh();
    });
  };

  const onRevoke = (fd: FormData) => {
    startTransition(async () => {
      await revokeApiKeyAction(fd);
      router.refresh();
    });
  };

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-sm font-semibold">API keys</h2>
          <p className="text-[11px] text-ink-500 mt-0.5">
            For the AutoCurb Chrome extension and programmatic integrations.
            Tokens are shown once at creation — save them in a password manager.
          </p>
        </div>
        <form action={onCreate} className="flex gap-2">
          <input
            type="text"
            name="name"
            placeholder="e.g. chrome-ext-alice"
            required
            className="input w-64"
          />
          <button type="submit" disabled={pending} className="btn-primary">
            {pending ? "Creating…" : "Create key"}
          </button>
        </form>
      </div>

      {newToken && (
        <div className="border-b border-ink-200 bg-emerald-50 p-4 text-sm">
          <p className="font-medium text-emerald-900">
            Token created — copy it now, it won&apos;t be shown again.
          </p>
          <p className="mt-2 font-mono text-xs bg-white rounded border border-emerald-200 p-2 select-all break-all">
            {newToken}
          </p>
          {tokenPrefix && (
            <p className="mt-1 text-xs text-emerald-700">
              Prefix for reference: {tokenPrefix}
            </p>
          )}
        </div>
      )}

      {error && (
        <div className="border-b border-ink-200 bg-rose-50 p-3 text-sm text-rose-800">
          ⚠ {error}
        </div>
      )}

      {keys.length === 0 ? (
        <p className="p-5 text-sm text-ink-500">
          No API keys yet. Create one to authenticate the Chrome extension.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="text-left font-medium px-4 py-2.5">Name</th>
              <th className="text-left font-medium px-4 py-2.5">Token</th>
              <th className="text-left font-medium px-4 py-2.5">Created</th>
              <th className="text-left font-medium px-4 py-2.5">Last used</th>
              <th className="text-left font-medium px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-200">
            {keys.map((k) => (
              <tr key={k.id} className="hover:bg-ink-50">
                <td className="px-4 py-2.5 font-medium">{k.name}</td>
                <td className="px-4 py-2.5 font-mono text-xs text-ink-600">
                  {k.token_prefix}…
                </td>
                <td className="px-4 py-2.5 text-xs text-ink-500 tabular">
                  {formatRelativeDate(k.created_at)}
                </td>
                <td className="px-4 py-2.5 text-xs text-ink-500 tabular">
                  {k.last_used_at ? formatRelativeDate(k.last_used_at) : "never"}
                </td>
                <td className="px-4 py-2.5">
                  {k.revoked_at ? (
                    <span className="badge bg-rose-100 text-rose-800">revoked</span>
                  ) : (
                    <span className="badge bg-emerald-100 text-emerald-800">active</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {!k.revoked_at && (
                    <form action={onRevoke} className="inline">
                      <input type="hidden" name="id" value={k.id} />
                      <button
                        type="submit"
                        className="btn-ghost text-xs text-rose-600 hover:text-rose-700"
                      >
                        Revoke
                      </button>
                    </form>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
