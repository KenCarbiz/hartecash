import type { Metadata } from "next";
import "../globals.css";

export const metadata: Metadata = {
  title: "AutoCurb — Sign in",
};

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen flex items-center justify-center bg-ink-100 px-4">
          <div className="w-full max-w-md">
            <div className="mb-6 flex items-center justify-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded bg-brand-600 text-white font-bold">
                A
              </span>
              <span className="text-lg font-semibold tracking-tight">AutoCurb</span>
            </div>
            {children}
          </div>
        </div>
      </body>
    </html>
  );
}
