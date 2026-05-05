"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

/** Sibling apps under the autocurb.io umbrella. The current app
 *  (AutoAcquisition) is rendered with a check; the rest are external
 *  links. URLs are placeholders until the parent shell publishes the
 *  real registry. */
interface AppEntry {
  key: string;
  name: string;
  blurb: string;
  href: string;
  external: boolean;
  badge?: string;
}

const CURRENT_KEY = "autoacquisition";

const APPS: AppEntry[] = [
  {
    key: CURRENT_KEY,
    name: "AutoAcquisition",
    blurb: "FSBO leads from FB Marketplace + Craigslist",
    href: "/",
    external: false,
  },
  {
    key: "autocurb",
    name: "AutoCurb",
    blurb: "Seller intake + cash offers",
    href: "https://autocurb.io",
    external: true,
  },
];

export function AppSwitcher({ variant = "sidebar" }: { variant?: "sidebar" | "topbar" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const trigger =
    variant === "sidebar"
      ? "flex h-7 w-7 items-center justify-center rounded text-ink-300 hover:bg-ink-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
      : "flex h-8 w-8 items-center justify-center rounded text-ink-600 hover:bg-ink-100 hover:text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500";

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Switch app"
        aria-haspopup="menu"
        aria-expanded={open}
        className={trigger}
        title="Switch app"
      >
        {/* 3x3 grid icon — universal "app launcher" affordance */}
        <svg
          viewBox="0 0 24 24"
          width="16"
          height="16"
          fill="currentColor"
          aria-hidden
        >
          <circle cx="5" cy="5" r="1.6" />
          <circle cx="12" cy="5" r="1.6" />
          <circle cx="19" cy="5" r="1.6" />
          <circle cx="5" cy="12" r="1.6" />
          <circle cx="12" cy="12" r="1.6" />
          <circle cx="19" cy="12" r="1.6" />
          <circle cx="5" cy="19" r="1.6" />
          <circle cx="12" cy="19" r="1.6" />
          <circle cx="19" cy="19" r="1.6" />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute z-20 mt-2 w-72 rounded-md border border-ink-200 bg-white p-2 text-ink-900 shadow-lg"
          style={
            variant === "sidebar"
              ? { left: 0, top: "100%" }
              : { right: 0, top: "100%" }
          }
        >
          <p className="px-2 py-1 text-[10px] uppercase tracking-wider text-ink-500">
            autocurb.io suite
          </p>
          <ul className="mt-1 space-y-0.5">
            {APPS.map((app) => {
              const isCurrent = app.key === CURRENT_KEY;
              const Inner = (
                <span className="flex items-start gap-3">
                  <span
                    className={`mt-0.5 flex h-7 w-7 items-center justify-center rounded text-xs font-bold ${
                      isCurrent
                        ? "bg-brand-600 text-white"
                        : "bg-ink-100 text-ink-700"
                    }`}
                  >
                    {app.name[0]}
                  </span>
                  <span className="flex flex-col leading-tight flex-1 min-w-0">
                    <span className="flex items-center gap-2 text-sm font-medium">
                      {app.name}
                      {isCurrent && (
                        <span className="text-[10px] uppercase tracking-wider text-brand-600">
                          Current
                        </span>
                      )}
                      {app.badge && (
                        <span className="rounded bg-ink-100 px-1.5 text-[10px] uppercase tracking-wider text-ink-600">
                          {app.badge}
                        </span>
                      )}
                    </span>
                    <span className="text-[11px] text-ink-500">{app.blurb}</span>
                  </span>
                  {app.external && (
                    <span className="mt-1 text-[10px] text-ink-400">↗</span>
                  )}
                </span>
              );
              return (
                <li key={app.key}>
                  {app.external ? (
                    <a
                      href={app.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => setOpen(false)}
                      className="block rounded p-2 hover:bg-ink-50"
                    >
                      {Inner}
                    </a>
                  ) : (
                    <Link
                      href={app.href}
                      onClick={() => setOpen(false)}
                      className="block rounded p-2 hover:bg-ink-50"
                    >
                      {Inner}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
