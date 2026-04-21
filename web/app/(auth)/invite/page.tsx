import Link from "next/link";
import { acceptInviteAction } from "@/app/(auth)/invite/actions";
import { AcceptInviteForm } from "@/components/auth/AcceptInviteForm";
import { previewInvitation } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function InvitePage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  if (!token) {
    return (
      <div className="panel p-6">
        <h1 className="text-lg font-semibold">Invite link missing</h1>
        <p className="mt-1 text-sm text-ink-500">
          This URL needs a <code>?token=</code> parameter.
        </p>
      </div>
    );
  }

  const preview = await previewInvitation(token);
  if ("error" in preview) {
    return (
      <div className="panel p-6">
        <h1 className="text-lg font-semibold">Invite unavailable</h1>
        <p className="mt-2 text-sm text-rose-700">{preview.error}</p>
        <Link
          href="/login"
          className="mt-5 inline-block btn-secondary"
        >
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="panel p-6">
      <h1 className="text-lg font-semibold">Join {preview.dealer_name ?? preview.dealer_id}</h1>
      <p className="mt-1 text-sm text-ink-500">
        {preview.invited_by_email
          ? `${preview.invited_by_email} invited you as a ${preview.role}.`
          : `You were invited to join as a ${preview.role}.`}
      </p>
      <p className="mt-1 text-xs text-ink-500">
        Signing in as <strong>{preview.email}</strong>.
      </p>
      <AcceptInviteForm action={acceptInviteAction} token={token} />
    </div>
  );
}
