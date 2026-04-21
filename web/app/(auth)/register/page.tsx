import Link from "next/link";
import { registerAction } from "@/app/(auth)/actions";
import { RegisterForm } from "@/components/auth/LoginForm";

export const dynamic = "force-dynamic";

export default function RegisterPage() {
  return (
    <div className="panel p-6">
      <h1 className="text-lg font-semibold">Create your dealer account</h1>
      <p className="mt-1 text-sm text-ink-500">
        Get your acquisition team on AutoCurb in under a minute.
      </p>
      <RegisterForm action={registerAction} />
      <p className="mt-6 text-xs text-ink-500">
        Already have an account?{" "}
        <Link href="/login" className="text-brand-600 hover:text-brand-700 font-medium">
          Sign in
        </Link>
      </p>
    </div>
  );
}
