import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { useQueryClient } from "@tanstack/react-query";
import {
  LayoutDashboard,
  MessageSquareText,
  FileText,
  Upload,
  Bell,
  Settings as SettingsIcon,
  Menu,
  X,
  LogOut,
  Users,
} from "lucide-react";
import { useLayout } from "../contexts/LayoutContext";
import { useAuth } from "../contexts/AuthContext";
import { ROUTES } from "../lib/routes";
import { BrandLogo } from "./BrandLogo";
import { prefetchClients } from "../hooks/useApi";
import { CreditBadge, CreditWidget } from "./credits";

/** Routes that benefit from client-list prefetch on hover. */
const CLIENT_PREFETCH_ROUTES = new Set(["/clients", "/chat", "/brief"]);

const NAV_GROUPS: {
  label: string;
  items: { href: string; label: string; icon: typeof LayoutDashboard }[];
}[] = [
  {
    label: "General",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/brief", label: "Meeting Brief", icon: FileText },
      { href: "/chat", label: "AI Copilot", icon: MessageSquareText },
      { href: "/alerts", label: "Alerts", icon: Bell },
      { href: "/clients", label: "Clients", icon: Users },
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
  const qc = useQueryClient();
  return (
    <nav className="flex flex-col gap-6" aria-label="Primary">
      {NAV_GROUPS.map((group) => (
        <div key={group.label} className="flex flex-col gap-1">
          <p className="px-3 text-xs font-medium text-slate-500">
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
                onMouseEnter={() => {
                  if (CLIENT_PREFETCH_ROUTES.has(href)) prefetchClients(qc);
                }}
                onClick={onNavigate}
                aria-current={isActive ? "page" : undefined}
                data-testid={`nav-link-${label.toLowerCase().replace(/\s+/g, "-")}`}
                className={`group flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? "bg-brand-50 text-brand-700 shadow-xs ring-1 ring-brand-100"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"
                }`}
              >
                <Icon
                  className={`h-4 w-4 flex-shrink-0 transition-colors ${
                    isActive
                      ? "text-brand-600"
                      : "text-slate-400 group-hover:text-slate-600"
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
  const router = useRouter();
  const { configured, user, signOut } = useAuth();
  const email = user?.email ?? "";
  const initials = email ? email.slice(0, 2).toUpperCase() : "FA";

  const handleSignOut = async () => {
    await signOut();
    router.push(ROUTES.login);
  };

  return (
    <div className="mt-auto border-t border-slate-100 pt-4">
      <div className="mb-4">
        <CreditWidget compact />
      </div>
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
          {initials}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-slate-950">
            {configured && email ? email : "Adviser"}
          </p>
          <p className="truncate text-xs text-slate-500">KritiFin workspace</p>
        </div>
      </div>
      {configured && user && (
        <button
          type="button"
          onClick={handleSignOut}
          data-testid="sign-out-button"
          className="mt-3 flex w-full items-center gap-2 rounded-xl px-2 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-950"
        >
          <LogOut className="h-4 w-4" aria-hidden />
          Sign out
        </button>
      )}
    </div>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { pageTitle, headerExtra } = useLayout();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  // Close the mobile drawer on route change.
  useEffect(() => {
    setDrawerOpen(false);
  }, [router.pathname]);

  // Drawer keyboard behaviour: Escape closes; Tab is trapped inside the
  // dialog (mirrors components/ui/Modal.tsx).
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setDrawerOpen(false);
        return;
      }
      if (e.key !== "Tab" || !drawerRef.current) return;
      const focusables = drawerRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  // Move focus into the drawer on open; restore it to the menu button on close.
  useEffect(() => {
    if (drawerOpen) {
      const focusables = drawerRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled])'
      );
      focusables?.[0]?.focus();
    } else {
      // Only restore if focus was left inside the removed drawer.
      if (document.activeElement === document.body) {
        menuButtonRef.current?.focus();
      }
    }
  }, [drawerOpen]);

  return (
    <div className="flex min-h-screen bg-[#F8FAFC] font-sans">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-xl focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden w-64 flex-shrink-0 flex-col gap-8 border-r border-slate-200 bg-white/85 p-6 backdrop-blur-xl md:flex">
        <Link href="/dashboard" className="flex items-center gap-2">
          <BrandLogo size="sm" />
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
            ref={drawerRef}
            className="absolute left-0 top-0 flex h-full w-72 flex-col gap-8 border-r border-slate-200 bg-white p-6 shadow-overlay"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation menu"
          >
            <div className="flex items-center justify-between">
              <Link href="/dashboard" className="flex items-center gap-2">
                <BrandLogo size="sm" />
              </Link>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="rounded-xl p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
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
        <header className="sticky top-0 z-30 flex flex-shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 py-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button
              ref={menuButtonRef}
              type="button"
              onClick={() => setDrawerOpen(true)}
              data-testid="mobile-menu-button"
              className="rounded-xl p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 md:hidden"
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" aria-hidden />
            </button>
            <h1 className="truncate text-lg font-semibold tracking-tight text-slate-950 sm:text-xl">
              {pageTitle}
            </h1>
          </div>
          <div className="flex max-w-[min(100%,42rem)] flex-wrap items-center justify-end gap-2 sm:gap-3">
            {headerExtra}
            <CreditBadge />
          </div>
        </header>
        <main
          id="main-content"
          data-testid="app-main"
          className="flex-1 overflow-auto p-4 animate-fade-in sm:p-6 lg:p-8"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
