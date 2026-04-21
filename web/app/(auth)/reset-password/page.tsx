import Link from "next/link";
import { resetPasswordAction } from "@/app/(auth)/reset-password/actions";
import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";

export const dynamic = "force-dynamic";

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  if (!token) {
    return (
      <div className="panel p-6">
        <h1 className="text-lg font-semibold">Missing reset token</h1>
        <p className="mt-1 text-sm text-ink-500">
          Use the link from your email.
        </p>
        <Link href="/forgot-password" className="mt-5 inline-block btn-secondary">
          Request a new link
        </Link>
      </div>
    );
  }

  return (
    <div className="panel p-6">
      <h1 className="text-lg font-semibold">Set a new password</h1>
      <p className="mt-1 text-sm text-ink-500">
        Choose a password at least 8 characters long.
      </p>
      <ResetPasswordForm action={resetPasswordAction} token={token} />
    </div>
  );
}
