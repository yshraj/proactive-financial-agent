import React from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";

/**
 * Shared split-screen layout for the login and signup pages. Left is a brand
 * panel (desktop only); right hosts the form. Built from existing tokens.
 */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen bg-white font-sans lg:grid-cols-2">
      {/* Brand panel — desktop only */}
      <div className="relative hidden flex-col justify-between overflow-hidden bg-brand-600 p-12 text-white lg:flex">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15 text-sm font-bold">
            J
          </span>
          <span className="text-sm font-semibold tracking-tight">Jarvis</span>
        </Link>
        <div className="relative">
          <Sparkles className="h-6 w-6 text-white/70" aria-hidden />
          <p className="mt-5 max-w-sm text-2xl font-semibold leading-snug tracking-tight">
            Spend less time reactive. More time advising.
          </p>
          <p className="mt-3 max-w-sm text-sm leading-relaxed text-white/70">
            Priorities, pre-meeting briefs, and ready-to-send emails — from your
            own client documents.
          </p>
        </div>
        <p className="text-xs text-white/50">
          Proactive AI for financial advisers
        </p>
      </div>

      {/* Form panel */}
      <div className="flex flex-col items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <Link href="/" className="mb-8 flex items-center gap-2 lg:hidden">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
              J
            </span>
            <span className="text-sm font-semibold tracking-tight text-gray-900">
              Jarvis
            </span>
          </Link>

          <h1 className="text-2xl font-semibold tracking-tight text-gray-900">
            {title}
          </h1>
          <p className="mt-1.5 text-sm text-gray-500">{subtitle}</p>

          <div className="mt-8">{children}</div>

          {footer && (
            <p className="mt-6 text-center text-sm text-gray-500">{footer}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default AuthShell;
