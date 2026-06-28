import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import {
  LayoutDashboard,
  MessageSquareText,
  FileText,
  Upload,
  Bell,
  Settings as SettingsIcon,
  Menu,
  X,
} from "lucide-react";
import { useLayout } from "../contexts/LayoutContext";

function Logo() {
  return (
    <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white shadow-xs">
      J
    </span>
  );
}

const NAV_GROUPS: {
  label: string;
  items: { href: string; label: string; icon: typeof LayoutDashboard }[];
}[] = [
  {
    label: "General",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/chat", label: "Ask Jarvis", icon: MessageSquareText },
      { href: "/brief", label: "Pre-meeting brief", icon: FileText },
      { href: "/alerts", label: "Alerts", icon: Bell },
    ],
  },
  {
    label: "Manage",
    items: [
      { href: "/admin", label: "Ingestion", icon: Upload },
      { href: "/settings", label: "Settings", icon: SettingsIcon },
    ],
  },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const router = useRouter();
  return (
    <nav className="flex flex-col gap-6" aria-label="Primary">
      {NAV_GROUPS.map((group) => (
        <div key={group.label} className="flex flex-col gap-1">
          <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
            {group.label}
          </p>
          {group.items.map(({ href, label, icon: Icon }) => {
            const isActive =
              router.pathname === href ||
              (href !== "/" && router.pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                aria-current={isActive ? "page" : undefined}
                className={`group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                }`}
              >
                <Icon
                  className={`h-4 w-4 flex-shrink-0 transition-colors ${
                    isActive
                      ? "text-brand-600"
                      : "text-gray-400 group-hover:text-gray-600"
                  }`}
                  aria-hidden
                />
                {label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function AccountMenu() {
  return (
    <div className="mt-auto flex items-center gap-3 border-t border-gray-100 pt-4">
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-200 text-xs font-semibold text-gray-700">
        FA
      </span>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-gray-900">Adviser</p>
        <p className="truncate text-xs text-gray-500">Jarvis workspace</p>
      </div>
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { pageTitle, headerExtra } = useLayout();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Close the mobile drawer on route change.
  useEffect(() => {
    setDrawerOpen(false);
  }, [router.pathname]);

  // Close drawer on Escape.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="flex min-h-screen bg-gray-50 font-sans">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden w-60 flex-shrink-0 flex-col gap-8 border-r border-gray-200 bg-white p-6 md:flex">
        <Link href="/dashboard" className="flex items-center gap-2">
          <Logo />
          <span className="text-sm font-semibold tracking-tight text-gray-900">
            Jarvis
          </span>
        </Link>
        <NavLinks />
        <AccountMenu />
      </aside>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-black/40 animate-fade-in"
            onClick={() => setDrawerOpen(false)}
            aria-hidden
          />
          <aside
            className="absolute left-0 top-0 flex h-full w-64 flex-col gap-8 border-r border-gray-200 bg-white p-6 shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation menu"
          >
            <div className="flex items-center justify-between">
              <Link href="/dashboard" className="flex items-center gap-2">
                <Logo />
                <span className="text-sm font-semibold tracking-tight text-gray-900">
                  Jarvis
                </span>
              </Link>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                aria-label="Close menu"
              >
                <X className="h-5 w-5" aria-hidden />
              </button>
            </div>
            <NavLinks onNavigate={() => setDrawerOpen(false)} />
            <AccountMenu />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex flex-shrink-0 items-center justify-between gap-3 border-b border-gray-200 bg-white/95 px-4 py-4 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 md:hidden"
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" aria-hidden />
            </button>
            <h1 className="truncate text-lg font-semibold tracking-tight text-gray-900 sm:text-xl">
              {pageTitle}
            </h1>
          </div>
          {headerExtra && (
            <div className="flex items-center gap-3">{headerExtra}</div>
          )}
        </header>
        <main id="main-content" className="flex-1 overflow-auto p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
