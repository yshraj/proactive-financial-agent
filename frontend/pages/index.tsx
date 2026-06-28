import Head from "next/head";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  MessageSquareText,
  FileText,
  Upload,
  Mail,
  Bell,
  ArrowRight,
  Check,
  Sparkles,
  Menu,
  X,
} from "lucide-react";
import { ButtonLink } from "../components/ui";
import { Reveal } from "../components/Reveal";
import { GET_STARTED_HREF, ROUTES } from "../lib/routes";
import { SITE_DESCRIPTION, SITE_NAME, SITE_TITLE, SITE_URL } from "../lib/seo";

const NAV_LINKS = [
  { href: "#features", label: "Features" },
  { href: "#how", label: "How it works" },
  { href: "#faq", label: "FAQ" },
];

const FEATURES = [
  {
    icon: LayoutDashboard,
    title: "Proactive dashboard",
    text: "See what's due in the next 30 days, ranked by priority — never miss a review or deadline.",
  },
  {
    icon: MessageSquareText,
    title: "Ask Jarvis",
    text: "Natural-language answers across your clients, alerts, and ingested documents.",
  },
  {
    icon: FileText,
    title: "Pre-meeting briefs",
    text: "A one-page brief with suggested talking points before every client meeting.",
  },
  {
    icon: Upload,
    title: "Smart ingestion",
    text: "Drop in fact-finds and notes; Jarvis extracts clients, dates, and follow-ups automatically.",
  },
  {
    icon: Mail,
    title: "Draft emails",
    text: "Generate personalised, ready-to-send emails for any alert in a single click.",
  },
  {
    icon: Bell,
    title: "Alerts & follow-ups",
    text: "Track overdue reviews and commitments so nothing slips through the cracks.",
  },
];

const STEPS = [
  {
    title: "Upload documents",
    text: "Add client fact-finds and meeting notes — PDF or Word. Duplicates are detected automatically.",
  },
  {
    title: "Jarvis extracts the signal",
    text: "Clients, review dates, deadlines, and follow-ups are structured and indexed for search.",
  },
  {
    title: "Act on priorities",
    text: "Work from a prioritised dashboard, generate briefs, and send drafted emails.",
  },
];

const BENEFITS = [
  "Spend less time on admin, more time advising",
  "Walk into every meeting fully prepared",
  "Stay on top of reviews and follow-up commitments",
  "Keep client knowledge searchable in one place",
];

const FAQS = [
  {
    q: "Do I need to connect my CRM?",
    a: "No. Upload your client documents directly and Jarvis builds the knowledge base for you — no integration required to get started.",
  },
  {
    q: "Which file types are supported?",
    a: "PDF and Word (.docx) — fact-finds, meeting notes, and similar documents up to 20 MB each.",
  },
  {
    q: "Is my data secure?",
    a: "Provider keys are configured securely on the server, and your documents live in your own database and vector store.",
  },
  {
    q: "How does Ask Jarvis answer questions?",
    a: "It combines your structured records (clients, alerts) with semantic search over your ingested documents, then synthesises a grounded answer with sources.",
  },
  {
    q: "Is there a login?",
    a: "Authentication is coming soon. For now, Get Started takes you straight into the app so you can explore everything.",
  },
];

function Logo() {
  return (
    <span className="flex items-center gap-2">
      <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white shadow-xs">
        J
      </span>
      <span className="text-sm font-semibold tracking-tight text-gray-900">Jarvis</span>
    </span>
  );
}

export default function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <>
      <Head>
        <title>{SITE_TITLE}</title>
        <meta name="description" content={SITE_DESCRIPTION} />
        <link rel="canonical" href={`${SITE_URL}/`} />
        <meta property="og:type" content="website" />
        <meta property="og:site_name" content={SITE_NAME} />
        <meta property="og:title" content={SITE_TITLE} />
        <meta property="og:description" content={SITE_DESCRIPTION} />
        <meta property="og:url" content={`${SITE_URL}/`} />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={SITE_TITLE} />
        <meta name="twitter:description" content={SITE_DESCRIPTION} />
      </Head>

      <div className="min-h-screen bg-white font-sans text-gray-700">
        {/* ── Top navigation ── */}
        <header className="sticky top-0 z-40 border-b border-gray-200 bg-white/90 backdrop-blur">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
            <Logo />
            <nav className="hidden items-center gap-8 md:flex" aria-label="Marketing">
              {NAV_LINKS.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  className="text-sm font-medium text-gray-600 transition-colors hover:text-gray-900"
                >
                  {l.label}
                </a>
              ))}
            </nav>
            <div className="flex items-center gap-3">
              <Link
                href={GET_STARTED_HREF}
                className="hidden text-sm font-medium text-gray-600 transition-colors hover:text-gray-900 sm:inline"
              >
                Sign in
              </Link>
              <ButtonLink href={GET_STARTED_HREF} size="sm">
                Get Started
              </ButtonLink>
              <button
                type="button"
                onClick={() => setMenuOpen(true)}
                className="rounded-lg p-2 text-gray-600 hover:bg-gray-100 hover:text-gray-900 md:hidden"
                aria-label="Open menu"
                aria-expanded={menuOpen}
              >
                <Menu className="h-5 w-5" aria-hidden />
              </button>
            </div>
          </div>
        </header>

        {/* Mobile navigation drawer */}
        {menuOpen && (
          <div className="fixed inset-0 z-50 md:hidden">
            <div
              className="absolute inset-0 bg-black/40 animate-fade-in"
              onClick={() => setMenuOpen(false)}
              aria-hidden
            />
            <div
              role="dialog"
              aria-modal="true"
              aria-label="Menu"
              className="absolute right-0 top-0 flex h-full w-72 flex-col gap-2 border-l border-gray-200 bg-white p-6 shadow-overlay"
            >
              <div className="mb-2 flex items-center justify-between">
                <Logo />
                <button
                  type="button"
                  onClick={() => setMenuOpen(false)}
                  className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                  aria-label="Close menu"
                >
                  <X className="h-5 w-5" aria-hidden />
                </button>
              </div>
              {NAV_LINKS.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  onClick={() => setMenuOpen(false)}
                  className="rounded-lg px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100"
                >
                  {l.label}
                </a>
              ))}
              <div className="mt-4 flex flex-col gap-3">
                <ButtonLink href={GET_STARTED_HREF} className="w-full">
                  Get Started
                </ButtonLink>
                <Link
                  href={GET_STARTED_HREF}
                  onClick={() => setMenuOpen(false)}
                  className="text-center text-sm font-medium text-gray-600 hover:text-gray-900"
                >
                  Sign in
                </Link>
              </div>
            </div>
          </div>
        )}

        <main>
          {/* ── Hero ── */}
          <section className="relative overflow-hidden bg-gradient-to-b from-brand-50/50 to-white">
            <div className="mx-auto max-w-3xl px-6 py-20 text-center sm:py-28">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-100 bg-white px-3 py-1 text-xs font-medium text-brand-700 shadow-xs">
                <Sparkles className="h-3.5 w-3.5" aria-hidden />
                Proactive AI for financial advisers
              </span>
              <h1 className="mt-6 text-4xl font-semibold tracking-tight text-gray-900 sm:text-5xl sm:leading-[1.1]">
                Spend less time reactive.
                <br className="hidden sm:block" /> More time advising.
              </h1>
              <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-gray-500 sm:text-lg">
                Jarvis turns your client documents into prioritised actions, pre-meeting
                briefs, and ready-to-send emails — so nothing slips and every meeting is
                prepared.
              </p>
              <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                <ButtonLink
                  href={GET_STARTED_HREF}
                  size="lg"
                  leftIcon={<ArrowRight className="h-4 w-4" aria-hidden />}
                >
                  Get Started
                </ButtonLink>
                <ButtonLink href="#how" variant="secondary" size="lg">
                  See how it works
                </ButtonLink>
              </div>
              <p className="mt-4 text-xs text-gray-400">
                No setup required — explore the full app instantly.
              </p>
            </div>
          </section>

          {/* ── Features ── */}
          <section id="features" className="scroll-mt-20 border-t border-gray-100 py-20 sm:py-24">
            <div className="mx-auto max-w-6xl px-6">
              <Reveal>
              <div className="mx-auto max-w-2xl text-center">
                <p className="overline">Features</p>
                <h2 className="mt-2 text-3xl font-semibold tracking-tight text-gray-900">
                  Everything you need to stay ahead of your book
                </h2>
                <p className="mt-3 text-base leading-relaxed text-gray-500">
                  One calm workspace that surfaces the right client, at the right moment,
                  with the right context.
                </p>
              </div>
              <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {FEATURES.map(({ icon: Icon, title, text }) => (
                  <div
                    key={title}
                    className="rounded-xl border border-gray-200 bg-white p-6 shadow-xs transition-shadow hover:shadow-card-hover"
                  >
                    <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                      <Icon className="h-5 w-5" aria-hidden />
                    </span>
                    <h3 className="mt-4 text-base font-semibold text-gray-900">{title}</h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-gray-500">{text}</p>
                  </div>
                ))}
              </div>
              </Reveal>
            </div>
          </section>

          {/* ── How it works ── */}
          <section id="how" className="scroll-mt-20 border-t border-gray-100 bg-gray-50/60 py-20 sm:py-24">
            <div className="mx-auto max-w-6xl px-6">
              <Reveal>
              <div className="mx-auto max-w-2xl text-center">
                <p className="overline">How it works</p>
                <h2 className="mt-2 text-3xl font-semibold tracking-tight text-gray-900">
                  From documents to action in three steps
                </h2>
              </div>
              <ol className="mt-12 grid grid-cols-1 gap-6 md:grid-cols-3">
                {STEPS.map((step, i) => (
                  <li
                    key={step.title}
                    className="rounded-xl border border-gray-200 bg-white p-6 shadow-xs"
                  >
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">
                      {i + 1}
                    </span>
                    <h3 className="mt-4 text-base font-semibold text-gray-900">{step.title}</h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-gray-500">{step.text}</p>
                  </li>
                ))}
              </ol>
              </Reveal>
            </div>
          </section>

          {/* ── Benefits ── */}
          <section className="border-t border-gray-100 py-20 sm:py-24">
            <div className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-12 px-6 lg:grid-cols-2">
              <div>
                <p className="overline">Why advisers choose Jarvis</p>
                <h2 className="mt-2 text-3xl font-semibold tracking-tight text-gray-900">
                  Be proactive, not reactive
                </h2>
                <p className="mt-3 text-base leading-relaxed text-gray-500">
                  Stop digging through notes and inboxes. Jarvis keeps the next best action
                  in front of you and handles the busywork.
                </p>
                <ul className="mt-6 space-y-3">
                  {BENEFITS.map((b) => (
                    <li key={b} className="flex items-start gap-3">
                      <span className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600">
                        <Check className="h-3.5 w-3.5" aria-hidden />
                      </span>
                      <span className="text-sm text-gray-700">{b}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-8">
                  <ButtonLink href={GET_STARTED_HREF} leftIcon={<ArrowRight className="h-4 w-4" aria-hidden />}>
                    Get Started
                  </ButtonLink>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                {[
                  { stat: "30 days", label: "of priorities, ranked" },
                  { stat: "1 click", label: "to a drafted email" },
                  { stat: "1 page", label: "pre-meeting brief" },
                  { stat: "0 setup", label: "to get started" },
                ].map((s) => (
                  <div
                    key={s.label}
                    className="rounded-xl border border-gray-200 bg-white p-6 shadow-xs"
                  >
                    <p className="text-2xl font-semibold tracking-tight text-gray-900">{s.stat}</p>
                    <p className="mt-1 text-sm text-gray-500">{s.label}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* ── FAQ ── */}
          <section id="faq" className="scroll-mt-20 border-t border-gray-100 bg-gray-50/60 py-20 sm:py-24">
            <div className="mx-auto max-w-3xl px-6">
              <Reveal>
              <div className="text-center">
                <p className="overline">FAQ</p>
                <h2 className="mt-2 text-3xl font-semibold tracking-tight text-gray-900">
                  Frequently asked questions
                </h2>
              </div>
              <div className="mt-10 divide-y divide-gray-200 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xs">
                {FAQS.map((item) => (
                  <details key={item.q} className="group px-6 [&_summary]:list-none">
                    <summary className="flex cursor-pointer items-center justify-between gap-4 py-4 text-sm font-medium text-gray-900">
                      {item.q}
                      <ArrowRight
                        className="h-4 w-4 flex-shrink-0 text-gray-400 transition-transform group-open:rotate-90"
                        aria-hidden
                      />
                    </summary>
                    <p className="pb-4 text-sm leading-relaxed text-gray-500">{item.a}</p>
                  </details>
                ))}
              </div>
              </Reveal>
            </div>
          </section>

          {/* ── Closing CTA ── */}
          <section className="border-t border-gray-100 py-20 sm:py-24">
            <div className="mx-auto max-w-3xl px-6 text-center">
              <Reveal>
              <h2 className="text-3xl font-semibold tracking-tight text-gray-900">
                Ready to get ahead of your day?
              </h2>
              <p className="mx-auto mt-3 max-w-xl text-base leading-relaxed text-gray-500">
                Jump straight in — upload a few documents and see your priorities,
                briefs, and draft emails come together.
              </p>
              <div className="mt-8 flex justify-center">
                <ButtonLink
                  href={GET_STARTED_HREF}
                  size="lg"
                  leftIcon={<ArrowRight className="h-4 w-4" aria-hidden />}
                >
                  Get Started
                </ButtonLink>
              </div>
              </Reveal>
            </div>
          </section>
        </main>

        {/* ── Footer ── */}
        <footer className="border-t border-gray-200 bg-white">
          <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-6 py-8 sm:flex-row">
            <Logo />
            <nav className="flex items-center gap-6" aria-label="Footer">
              <Link href={ROUTES.dashboard} className="text-sm text-gray-500 transition-colors hover:text-gray-900">
                Dashboard
              </Link>
              <Link href={ROUTES.chat} className="text-sm text-gray-500 transition-colors hover:text-gray-900">
                Ask Jarvis
              </Link>
              <a href="#features" className="text-sm text-gray-500 transition-colors hover:text-gray-900">
                Features
              </a>
            </nav>
            <p className="text-xs text-gray-400">
              © {new Date().getFullYear()} Jarvis. All rights reserved.
            </p>
          </div>
        </footer>
      </div>
    </>
  );
}
