import Link from "next/link";
import { forgotPasswordAction } from "@/app/(auth)/forgot-password/actions";
import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";

export const dynamic = "force-dynamic";

export default function ForgotPasswordPage() {
  return (
    <div className="panel p-6">
      <h1 className="text-lg font-semibold">Forgot your password?</h1>
      <p className="mt-1 text-sm text-ink-500">
        Enter your email and we&apos;ll send a link to reset it.
      </p>
      <ForgotPasswordForm action={forgotPasswordAction} />
      <p className="mt-6 text-xs text-ink-500">
        Remembered it?{" "}
        <Link
          href="/login"
          className="text-brand-600 hover:text-brand-700 font-medium"
        >
          Sign in
        </Link>
      </p>
    </div>
  );
}
