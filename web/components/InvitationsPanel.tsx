"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import {
  createInviteAction,
  revokeInviteAction,
} from "@/app/settings/invite-actions";
import type { InvitationRow } from "@/lib/api";
import { formatRelativeDate } from "@/lib/api";

export function InvitationsPanel({
  invites,
  appOrigin,
}: {
  invites: InvitationRow[];
  appOrigin: string;
}) {
  const [newToken, setNewToken] = useState<string | null>(null);
  const [newUrl, setNewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  const onInvite = (fd: FormData) => {
    startTransition(async () => {
      const res = await createInviteAction(fd);
      if (res.error) {
        setError(res.error);
        setNewToken(null);
        setNewUrl(null);
      } else {
        setError(null);
        setNewToken(res.token);
        setNewUrl(res.url);
      }
      router.refresh();
    });
  };

  const onRevoke = (fd: FormData) => {
    startTransition(async () => {
      await revokeInviteAction(fd);
      router.refresh();
    });
  };

  const fullUrl = newUrl ? `${appOrigin}${newUrl}` : null;

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-sm font-semibold">Team invitations</h2>
          <p className="text-[11px] text-ink-500 mt-0.5">
            Admins can invite teammates. One-time link; expires in 14 days.
          </p>
        </div>
        <form action={onInvite} className="flex gap-2">
          <input
            type="email"
            name="email"
            placeholder="teammate@yourdealer.com"
            required
            className="input w-64"
          />
          <select name="role" defaultValue="member" className="input w-28">
            <option value="member">Member</option>
            <option value="admin">Admin</option>
          </select>
          <button type="submit" disabled={pending} className="btn-primary">
            {pending ? "Sending…" : "Send invite"}
          </button>
        </form>
      </div>

      {fullUrl && (
        <div className="border-b border-ink-200 bg-emerald-50 p-4 text-sm">
          <p className="font-medium text-emerald-900">
            Invite ready — share this link:
          </p>
          <p className="mt-2 font-mono text-xs bg-white rounded border border-emerald-200 p-2 select-all break-all">
            {fullUrl}
          </p>
          <p className="mt-1 text-xs text-emerald-700">
            (Token is embedded — don&apos;t share publicly.) Raw token for
            reference: <code>{newToken}</code>
          </p>
        </div>
      )}

      {error && (
        <div className="border-b border-ink-200 bg-rose-50 p-3 text-sm text-rose-800">
          ⚠ {error}
        </div>
      )}

      {invites.length === 0 ? (
        <p className="p-5 text-sm text-ink-500">No invites yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="text-left font-medium px-4 py-2.5">Email</th>
              <th className="text-left font-medium px-4 py-2.5">Role</th>
              <th className="text-left font-medium px-4 py-2.5">Status</th>
              <th className="text-left font-medium px-4 py-2.5">Sent</th>
              <th className="text-left font-medium px-4 py-2.5">Expires</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-200">
            {invites.map((inv) => {
              const status = inv.revoked_at
                ? "revoked"
                : inv.accepted_at
                  ? "accepted"
                  : "pending";
              const statusBadge: Record<string, string> = {
                accepted: "bg-emerald-100 text-emerald-800",
                revoked: "bg-rose-100 text-rose-800",
                pending: "bg-amber-100 text-amber-800",
              };
              return (
                <tr key={inv.id} className="hover:bg-ink-50">
                  <td className="px-4 py-2.5">{inv.email}</td>
                  <td className="px-4 py-2.5 text-ink-700">{inv.role}</td>
                  <td className="px-4 py-2.5">
                    <span className={`badge ${statusBadge[status]}`}>{status}</span>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-ink-500 tabular">
                    {formatRelativeDate(inv.created_at)}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-ink-500 tabular">
                    {formatRelativeDate(inv.expires_at)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {status === "pending" && (
                      <form action={onRevoke} className="inline">
                        <input type="hidden" name="id" value={inv.id} />
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
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
