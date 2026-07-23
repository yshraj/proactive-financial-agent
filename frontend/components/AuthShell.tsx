import React from "react";
import Link from "next/link";
import { Lock, ShieldCheck, Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { BrandLogo } from "./BrandLogo";

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
    <div className="grid min-h-screen bg-[#F8FAFC] font-sans lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-slate-950 p-12 text-white xl:p-16 lg:flex">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_24%_20%,rgba(59,111,255,0.42),transparent_34%),radial-gradient(circle_at_76%_72%,rgba(124,58,237,0.24),transparent_30%),linear-gradient(135deg,#020617_0%,#0F172A_58%,#111827_100%)]" />
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue-300/50 to-transparent" />
        <Link href="/" className="relative flex items-center gap-3">
          <BrandLogo size="md" wordmarkClassName="text-white text-base" />
        </Link>
        <div className="relative mx-auto w-full max-w-2xl">
          <div className="mb-10 rounded-[2rem] border border-white/15 bg-white/10 p-4 shadow-overlay backdrop-blur-xl xl:p-5">
            <div className="rounded-[1.5rem] bg-white p-6 text-slate-950 xl:p-7">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-base font-semibold">Today&apos;s attention</p>
                  <p className="mt-1 text-sm text-slate-500">Prioritized client work</p>
                </div>
                <span className="rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">
                  Live
                </span>
              </div>
              <div className="mt-6 grid grid-cols-3 gap-3">
                {[
                  ["Reviews", "18"],
                  ["Follow-ups", "7"],
                  ["Compliance", "4"],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                    <p className="text-sm text-slate-500">{label}</p>
                    <p className="mt-2 text-3xl font-semibold tracking-tight">{value}</p>
                  </div>
                ))}
              </div>
              <div className="mt-6 space-y-3">
                {["Maya Shah review overdue", "Draft follow-up for Oliver Reed", "Prepare protection talking points"].map((item) => (
                  <div key={item} className="flex items-center gap-3 rounded-2xl border border-slate-100 px-4 py-3 text-sm text-slate-600">
                    <span className="h-2 w-2 rounded-full bg-brand-600" />
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </div>
          <Sparkles className="h-7 w-7 text-blue-200" aria-hidden />
          <p className="mt-5 max-w-xl text-4xl font-semibold leading-tight tracking-[-0.04em] xl:text-5xl">
            Stay ahead of every client.
          </p>
          <p className="mt-5 max-w-lg text-base leading-7 text-slate-300">
            KritiFin turns client intelligence, meeting preparation, and
            compliance signals into a calm adviser workspace.
          </p>
          <div className="mt-7 flex flex-wrap gap-3 text-sm text-slate-300">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2">
              <ShieldCheck className="h-4 w-4" aria-hidden />
              Secure workspace
            </span>
            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2">
              <Lock className="h-4 w-4" aria-hidden />
              Source-grounded AI
            </span>
          </div>
        </div>
        <p className="relative text-sm text-slate-400">
          The AI operating system for financial advisers
        </p>
      </div>

      <div className="relative flex flex-col items-center justify-center overflow-hidden px-6 py-12">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_18%,rgba(59,111,255,0.08),transparent_32%),linear-gradient(180deg,#FFFFFF_0%,#F8FAFC_100%)]" />
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="relative w-full max-w-lg rounded-[2rem] border border-slate-200 bg-white p-8 shadow-[0_24px_70px_-48px_rgba(15,23,42,0.55)] sm:p-10"
        >
          <Link href="/" className="mb-10 flex items-center gap-2 lg:hidden">
            <BrandLogo size="sm" />
          </Link>

          <h1 className="text-3xl font-semibold tracking-[-0.04em] text-slate-950">
            {title}
          </h1>
          <p className="mt-3 text-base leading-7 text-slate-500">{subtitle}</p>

          <div className="mt-9">{children}</div>

          {footer && (
            <p className="mt-8 text-center text-sm text-slate-500">{footer}</p>
          )}
        </motion.div>
      </div>
    </div>
  );
}

export default AuthShell;
