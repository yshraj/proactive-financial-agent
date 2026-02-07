import React from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { useLayout } from "../contexts/LayoutContext";

function Logo() {
  return (
    <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-sky-600 text-white shadow-sm">
      <span className="text-sm font-bold">J</span>
    </span>
  );
}

const SIDEBAR_NAV: { href: string; label: string }[] = [
  { href: "/", label: "Dashboard" },
  { href: "/chat", label: "Ask Jarvis" },
  { href: "/brief", label: "Pre-meeting brief" },
  { href: "/admin", label: "Ingestion" },
  { href: "/alerts", label: "Alerts" },
  { href: "/settings", label: "Settings" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { pageTitle, headerExtra } = useLayout();

  return (
    <div className="flex min-h-screen bg-gray-50 font-sans">
      <aside className="flex w-60 flex-shrink-0 flex-col gap-8 border-r border-gray-200 bg-white p-6">
        <Link href="/" className="flex items-center gap-2">
          <Logo />
          <span className="text-sm font-semibold tracking-tight text-gray-900">Jarvis</span>
        </Link>
        <nav className="flex flex-col gap-0.5">
          {SIDEBAR_NAV.map(({ href, label }) => {
            const isActive =
              router.pathname === href || (href !== "/" && router.pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-sky-50 text-sky-600"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                {label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-shrink-0 items-center justify-between gap-4 border-b border-gray-200 bg-white px-8 py-5">
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">{pageTitle}</h1>
          {headerExtra && <div className="flex items-center gap-4">{headerExtra}</div>}
        </header>
        <main className="flex-1 overflow-auto p-8">{children}</main>
      </div>
    </div>
  );
}
