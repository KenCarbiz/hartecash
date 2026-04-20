import Link from "next/link";
import type { ReactNode } from "react";

interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
}

function Icon({ path }: { path: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
      aria-hidden
    >
      <path d={path} />
    </svg>
  );
}

const NAV: NavItem[] = [
  {
    href: "/",
    label: "Dashboard",
    icon: <Icon path="M3 12l9-9 9 9M5 10v10h14V10" />,
  },
  {
    href: "/listings",
    label: "Listings",
    icon: <Icon path="M3 6h18M3 12h18M3 18h18" />,
  },
  {
    href: "/leads",
    label: "Leads",
    icon: <Icon path="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2M12 11a4 4 0 100-8 4 4 0 000 8z" />,
  },
  {
    href: "/sources",
    label: "Sources",
    icon: <Icon path="M4 7h16M4 12h16M4 17h16" />,
  },
  {
    href: "/settings",
    label: "Settings",
    icon: <Icon path="M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 01-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.9.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.9 1.7 1.7 0 00-1.5-1H3a2 2 0 010-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.9l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.9.3H9a1.7 1.7 0 001-1.5V3a2 2 0 014 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.9-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.9V9a1.7 1.7 0 001.5 1H21a2 2 0 010 4h-.1a1.7 1.7 0 00-1.5 1z" />,
  },
];

function Sidebar() {
  return (
    <aside className="hidden md:flex h-screen w-60 flex-col border-r border-ink-200 bg-ink-900 text-ink-100 sticky top-0">
      <div className="flex h-14 items-center gap-2 px-5 border-b border-ink-800">
        <span className="flex h-7 w-7 items-center justify-center rounded bg-brand-600 text-white text-sm font-bold">
          A
        </span>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold">AutoCurb</span>
          <span className="text-[10px] uppercase tracking-wider text-ink-400">
            Acquisitions
          </span>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-4">
        <ul className="space-y-0.5">
          {NAV.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm text-ink-300 hover:bg-ink-800 hover:text-white"
              >
                <span className="text-ink-400">{item.icon}</span>
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <div className="border-t border-ink-800 px-3 py-3 text-xs">
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 flex items-center justify-center rounded-full bg-ink-700 text-ink-200 text-xs font-medium">
            D
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-ink-100">Demo Dealer</span>
            <span className="text-ink-500 text-[10px]">demo-dealer</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

function MobileTopbar() {
  return (
    <header className="md:hidden sticky top-0 z-10 flex h-12 items-center justify-between border-b border-ink-200 bg-white px-4">
      <Link href="/" className="flex items-center gap-2 font-semibold">
        <span className="flex h-6 w-6 items-center justify-center rounded bg-brand-600 text-white text-xs font-bold">
          A
        </span>
        AutoCurb
      </Link>
      <nav className="flex items-center gap-3 text-sm text-ink-600">
        <Link href="/listings">Listings</Link>
        <Link href="/leads">Leads</Link>
      </nav>
    </header>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 min-w-0">
        <MobileTopbar />
        <div className="mx-auto max-w-7xl px-5 sm:px-8 py-6">{children}</div>
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
