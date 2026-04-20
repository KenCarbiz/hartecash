import Link from "next/link";

export function Nav() {
  return (
    <header className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 flex h-14 items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span className="inline-block h-6 w-6 rounded bg-brand-600" aria-hidden />
          AutoCurb
        </Link>
        <nav className="flex items-center gap-6 text-sm">
          <Link href="/" className="hover:text-brand-600">
            Dashboard
          </Link>
          <Link href="/listings" className="hover:text-brand-600">
            Listings
          </Link>
        </nav>
      </div>
    </header>
  );
}
