import Link from "next/link";
import { loginAction } from "@/app/(auth)/actions";
import { LoginForm } from "@/components/auth/LoginForm";

export const dynamic = "force-dynamic";

export default function LoginPage() {
  return (
    <div className="panel p-6">
      <h1 className="text-lg font-semibold">Sign in</h1>
      <p className="mt-1 text-sm text-ink-500">
        Welcome back. Sign in to your acquisition dashboard.
      </p>
      <LoginForm action={loginAction} />
      <p className="mt-6 text-xs text-ink-500">
        Don&apos;t have an account?{" "}
        <Link href="/register" className="text-brand-600 hover:text-brand-700 font-medium">
          Create one
        </Link>
      </p>
    </div>
  );
}
