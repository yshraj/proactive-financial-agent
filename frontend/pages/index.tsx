import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  Bell,
  Check,
  CheckCircle2,
  ChevronRight,
  FileSearch,
  FileText,
  Lock,
  Menu,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
  Upload,
  Workflow,
  X,
} from "lucide-react";
import { BrandLogo } from "../components/BrandLogo";
import { ButtonLink } from "../components/ui";
import { useAuth } from "../contexts/AuthContext";
import { GET_STARTED_HREF, ROUTES } from "../lib/routes";
import { SITE_DESCRIPTION, SITE_NAME, SITE_TITLE, SITE_URL } from "../lib/seo";

const NAV_LINKS = [
  { href: "#capabilities", label: "Capabilities" },
  { href: "#workflow", label: "Workflow" },
  { href: "#security", label: "Security" },
  { href: "#faq", label: "FAQ" },
];

// JSON-LD for rich results. Kept factual: no ratings/prices we don't have.
const STRUCTURED_DATA = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: SITE_NAME,
  url: `${SITE_URL}/`,
  description: SITE_DESCRIPTION,
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  image: `${SITE_URL}/og-image.png`,
  audience: {
    "@type": "BusinessAudience",
    audienceType: "UK financial advisers",
  },
};

const CAPABILITIES = [
  { icon: BarChart3, title: "Client Intelligence", text: "See reviews, risks, opportunities, and relationship context in one calm workspace." },
  { icon: FileText, title: "Meeting Preparation", text: "Generate executive briefs, talking points, action lists, and draft emails before every review." },
  { icon: ShieldCheck, title: "Compliance", text: "Surface overdue reviews, follow-up commitments, and sensitive client actions before they slip." },
  { icon: FileSearch, title: "Document Intelligence", text: "Turn fact-finds, notes, and PDFs into searchable client knowledge with grounded sources." },
  { icon: MessageSquareText, title: "AI Copilot", text: "Ask precise questions across your book of business without turning the product into a chatbot." },
  { icon: Workflow, title: "Workflow Automation", text: "Move from signal to next action with prioritized timelines and ready-to-send communication." },
];

const SHOWCASE = [
  { title: "Dashboard", text: "Know what matters today across reviews, follow-ups, compliance items, and upcoming meetings." },
  { title: "AI Workspace", text: "Ask questions with citations, source previews, and adviser-grade prompts." },
  { title: "Meeting Brief", text: "Walk into client meetings with context, risk notes, talking points, and next actions." },
  { title: "Document Intelligence", text: "Upload documents once and let KritiFin structure, index, and connect the useful signal." },
];

const STEPS = [
  "Upload Documents",
  "AI Understands Client Data",
  "Priorities Are Generated",
  "Adviser Takes Action",
];

const FAQS = [
  {
    q: "Is KritiFin an AI chatbot?",
    a: "No. AI is one capability inside a broader operating system for client intelligence, meeting preparation, compliance, and adviser workflows.",
  },
  {
    q: "Which files can advisers upload?",
    a: "The current workspace supports PDF and Word documents up to 20 MB, including fact-finds, meeting notes, and client records.",
  },
  {
    q: "How are answers grounded?",
    a: "KritiFin combines structured client records with semantic search over ingested documents, then shows sources alongside AI-generated answers.",
  },
  {
    q: "Can I try it without configuring authentication?",
    a: "Yes. In local or demo environments without Supabase auth configured, the login page lets you continue into the app.",
  },
];

function SectionHeading({
  eyebrow,
  title,
  text,
}: {
  eyebrow: string;
  title: string;
  text?: string;
}) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="ui-label text-brand-600">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-4xl">
        {title}
      </h2>
      {text && <p className="mt-4 text-base leading-7 text-slate-500">{text}</p>}
    </div>
  );
}

function DashboardPreview() {
  const priorities = [
    ["1", "Maya Shah", "Annual review overdue", "High"],
    ["2", "Oliver Reed", "Cash balance above target", "Medium"],
    ["3", "Aisha Khan", "Protection gap to discuss", "High"],
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15, duration: 0.5, ease: "easeOut" }}
      className="relative mx-auto mt-14 max-w-6xl"
    >
      <div className="absolute -left-6 top-16 hidden rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-card backdrop-blur lg:block">
        <p className="text-xs font-medium text-slate-500">Reviews due</p>
        <p className="mt-1 text-3xl font-semibold tracking-tight text-slate-950">18</p>
        <p className="mt-1 text-xs text-emerald-600">6 ready this week</p>
      </div>
      <div className="absolute -right-4 bottom-16 hidden rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-card backdrop-blur lg:block">
        <p className="text-xs font-medium text-slate-500">Documents processed</p>
        <p className="mt-1 text-3xl font-semibold tracking-tight text-slate-950">1,284</p>
        <p className="mt-1 text-xs text-brand-600">99.2% indexed</p>
      </div>
      <div className="overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-[0_30px_80px_-55px_rgba(15,23,42,0.6)]">
        <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/80 px-5 py-4">
          <BrandLogo size="sm" />
          <div className="hidden items-center gap-2 md:flex">
            {["Dashboard", "Clients", "Compliance", "AI Copilot"].map((item) => (
              <span key={item} className="rounded-full px-3 py-1 text-xs font-medium text-slate-500">
                {item}
              </span>
            ))}
          </div>
        </div>
        <div className="grid gap-px bg-slate-100 lg:grid-cols-[1fr_360px]">
          <div className="bg-white p-6 sm:p-8">
            <p className="text-sm font-medium text-slate-500">Good morning, James.</p>
            <h3 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-slate-950">
              Here&apos;s what deserves your attention today.
            </h3>
            <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Reviews Due", "18"],
                ["Follow-ups", "7"],
                ["Awaiting Response", "11"],
                ["Compliance Items", "4"],
              ].map(([label, value]) => (
                <div key={label} className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                  <p className="text-xs text-slate-500">{label}</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-950">{value}</p>
                </div>
              ))}
            </div>
            <div className="mt-8 rounded-2xl border border-slate-200">
              <div className="border-b border-slate-100 px-4 py-3">
                <p className="text-sm font-semibold text-slate-950">Priority timeline</p>
              </div>
              <div className="divide-y divide-slate-100">
                {priorities.map(([rank, client, note, priority]) => (
                  <div key={client} className="flex items-center gap-3 px-4 py-3">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700">
                      {rank}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-slate-950">{client}</p>
                      <p className="truncate text-xs text-slate-500">{note}</p>
                    </div>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                      {priority}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="bg-slate-50 p-6 sm:p-8">
            <div className="rounded-2xl border border-ai-100 bg-white p-5 shadow-xs">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-ai-600" aria-hidden />
                <p className="text-sm font-semibold text-slate-950">AI recommendation</p>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                Prioritize the Shah review. Recent notes mention retirement income concern and a pending ISA transfer.
              </p>
              <div className="mt-4 rounded-xl bg-ai-50 p-3 text-xs text-ai-700">
                Sources: meeting notes, fact-find, review history
              </div>
            </div>
            <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-5">
              <p className="text-sm font-semibold text-slate-950">Upcoming meetings</p>
              <div className="mt-4 space-y-3">
                {["Portfolio review", "Protection planning", "Tax year close"].map((item) => (
                  <div key={item} className="flex items-center gap-3">
                    <span className="h-2 w-2 rounded-full bg-brand-600" />
                    <span className="text-sm text-slate-600">{item}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const { configured, loading, user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!configured || loading || !user) return;
    router.replace(ROUTES.dashboard);
  }, [configured, loading, router, user]);

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
        <meta property="og:image" content={`${SITE_URL}/og-image.png`} />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:image:alt" content="KritiFin — the AI operating system for financial advisers" />
        <meta property="og:locale" content="en_GB" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={SITE_TITLE} />
        <meta name="twitter:description" content={SITE_DESCRIPTION} />
        <meta name="twitter:image" content={`${SITE_URL}/og-image.png`} />
        <script
          type="application/ld+json"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
        />
      </Head>

      <div className="min-h-screen bg-[#F8FAFC] font-sans text-slate-700">
        <header className="sticky top-0 z-40 border-b border-white/70 bg-white/75 backdrop-blur-xl">
          <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
            <BrandLogo size="sm" />
            <nav className="hidden items-center gap-7 md:flex" aria-label="Marketing">
              {NAV_LINKS.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-950"
                >
                  {l.label}
                </a>
              ))}
            </nav>
            <div className="flex items-center gap-3">
              <Link href={ROUTES.login} className="hidden text-sm font-medium text-slate-600 transition-colors hover:text-slate-950 sm:inline">
                Sign in
              </Link>
              <ButtonLink href={GET_STARTED_HREF} size="sm">
                Start Free
              </ButtonLink>
              <button
                type="button"
                onClick={() => setMenuOpen(true)}
                className="rounded-xl p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-950 md:hidden"
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
              className="absolute right-0 top-0 flex h-full w-72 flex-col gap-2 border-l border-slate-200 bg-white p-6 shadow-overlay"
            >
              <div className="mb-2 flex items-center justify-between">
                <BrandLogo size="sm" />
                <button
                  type="button"
                  onClick={() => setMenuOpen(false)}
                  className="rounded-xl p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
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
                  className="rounded-xl px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100"
                >
                  {l.label}
                </a>
              ))}
              <div className="mt-4 flex flex-col gap-3">
                <ButtonLink href={GET_STARTED_HREF} className="w-full">
                  Start Free
                </ButtonLink>
                <Link
                  href={ROUTES.login}
                  onClick={() => setMenuOpen(false)}
                  className="text-center text-sm font-medium text-slate-600 hover:text-slate-950"
                >
                  Sign in
                </Link>
              </div>
            </div>
          </div>
        )}

        <main data-testid="landing-page">
          <section className="relative overflow-hidden" data-testid="landing-hero">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(37,99,235,0.13),transparent_38%),linear-gradient(180deg,#FFFFFF_0%,#F8FAFC_72%)]" />
            <div className="relative mx-auto max-w-7xl px-6 pb-20 pt-20 text-center sm:pt-28">
              <motion.span
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="inline-flex items-center gap-1.5 rounded-full border border-brand-100 bg-white px-3 py-1 text-xs font-medium text-brand-700 shadow-xs"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden />
                The AI operating system for financial advisers
              </motion.span>
              <h1 className="mx-auto mt-6 max-w-4xl text-5xl font-semibold tracking-[-0.06em] text-slate-950 sm:text-7xl sm:leading-[0.98]">
                Know who to contact. What to review. What to do next.
              </h1>
              <p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-slate-500 sm:text-lg">
                KritiFin brings together client intelligence, meeting preparation,
                compliance, and AI into one proactive workspace.
              </p>
              <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                <ButtonLink
                  href={GET_STARTED_HREF}
                  size="lg"
                  leftIcon={<ArrowRight className="h-4 w-4" aria-hidden />}
                >
                  Start Free
                </ButtonLink>
                <ButtonLink href="#workflow" variant="secondary" size="lg">
                  Book Demo
                </ButtonLink>
              </div>
              <DashboardPreview />
            </div>
          </section>

          <section id="capabilities" data-testid="landing-capabilities" className="scroll-mt-20 border-t border-slate-200/70 bg-white py-20 sm:py-24">
            <div className="mx-auto max-w-7xl px-6">
              <SectionHeading
                eyebrow="Trusted capabilities"
                title="One operating layer for proactive advice"
                text="KritiFin keeps the adviser workflow centered on clients, not scattered across documents, inboxes, and manual reminders."
              />
              <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {CAPABILITIES.map(({ icon: Icon, title, text }, index) => (
                  <motion.div
                    key={title}
                    initial={{ opacity: 0, y: 10 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-80px" }}
                    transition={{ delay: index * 0.04, duration: 0.28 }}
                    className="rounded-3xl border border-slate-200 bg-white p-6 shadow-xs transition-all hover:-translate-y-1 hover:shadow-card-hover"
                  >
                    <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
                      <Icon className="h-5 w-5" aria-hidden />
                    </span>
                    <h3 className="mt-5 text-base font-semibold text-slate-950">{title}</h3>
                    <p className="mt-2 text-sm leading-6 text-slate-500">{text}</p>
                  </motion.div>
                ))}
              </div>
            </div>
          </section>

          <section className="border-t border-slate-200/70 py-20 sm:py-24">
            <div className="mx-auto grid max-w-7xl grid-cols-1 gap-10 px-6 lg:grid-cols-[0.85fr_1.15fr] lg:items-center">
              <div>
                <p className="ui-label text-brand-600">Problem statement</p>
                <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-4xl">
                  Advice teams do not need more noise. They need priority.
                </h2>
                <p className="mt-4 text-base leading-7 text-slate-500">
                  Reviews, compliance obligations, client concerns, and document updates
                  are often spread across disconnected systems. KritiFin turns that
                  complexity into a clear daily operating rhythm.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {["Never miss another review.", "Stay ahead of every client.", "From insight to action.", "Know what matters today."].map((item) => (
                  <div key={item} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-xs">
                    <CheckCircle2 className="h-5 w-5 text-emerald-500" aria-hidden />
                    <p className="mt-4 text-lg font-semibold tracking-tight text-slate-950">{item}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="border-t border-slate-200/70 bg-white py-20 sm:py-24">
            <div className="mx-auto max-w-7xl px-6">
              <SectionHeading
                eyebrow="Feature showcase"
                title="Designed around the adviser day"
                text="Each workspace is focused, source-aware, and built for action."
              />
              <div className="mt-12 grid gap-4 lg:grid-cols-4">
                {SHOWCASE.map((item, index) => (
                  <div key={item.title} className="rounded-3xl border border-slate-200 bg-slate-50/60 p-6">
                    <span className="text-xs font-semibold text-brand-600">0{index + 1}</span>
                    <h3 className="mt-4 text-lg font-semibold tracking-tight text-slate-950">{item.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-slate-500">{item.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section id="workflow" className="scroll-mt-20 border-t border-slate-200/70 py-20 sm:py-24">
            <div className="mx-auto max-w-7xl px-6">
              <SectionHeading
                eyebrow="How KritiFin works"
                title="From documents to prepared action"
              />
              <ol className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-4">
                {STEPS.map((step, i) => (
                  <li key={step} className="relative rounded-3xl border border-slate-200 bg-white p-6 shadow-xs">
                    <span className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-950 text-sm font-semibold text-white">
                      {i + 1}
                    </span>
                    <h3 className="mt-5 text-base font-semibold text-slate-950">{step}</h3>
                    {i < STEPS.length - 1 && (
                      <ChevronRight className="absolute right-5 top-7 hidden h-4 w-4 text-slate-300 md:block" aria-hidden />
                    )}
                  </li>
                ))}
              </ol>
            </div>
          </section>

          <section id="security" className="scroll-mt-20 border-t border-slate-200/70 bg-slate-950 py-20 text-white sm:py-24">
            <div className="mx-auto grid max-w-7xl grid-cols-1 gap-10 px-6 lg:grid-cols-2 lg:items-center">
              <div>
                <p className="ui-label text-blue-200">Security & privacy</p>
                <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
                  Built for sensitive client work.
                </h2>
                <p className="mt-4 text-base leading-7 text-slate-300">
                  KritiFin is designed around professional trust: source-grounded
                  answers, clear data boundaries, and a workflow that keeps advisers
                  in control of every client action.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                {[
                  [Lock, "Access control"],
                  [ShieldCheck, "Grounded answers"],
                  [Bell, "Audit-ready alerts"],
                ].map(([Icon, label]) => {
                  const SafeIcon = Icon as typeof Lock;
                  return (
                  <div key={String(label)} className="rounded-3xl border border-white/10 bg-white/5 p-5">
                    <SafeIcon className="h-5 w-5 text-blue-200" aria-hidden />
                    <p className="mt-4 text-sm font-medium text-white">{String(label)}</p>
                  </div>
                  );
                })}
              </div>
            </div>
          </section>

          <section className="border-t border-slate-200/70 bg-white py-20 sm:py-24">
            <div className="mx-auto max-w-4xl px-6 text-center">
              <p className="ui-label text-brand-600">Brand story</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-4xl">
                Inspired by meaningful work.
              </h2>
              <p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-slate-500">
                Kriti comes from the Sanskrit word कृति, meaning creation,
                achievement, and meaningful work. KritiFin is inspired by that
                philosophy: helping financial advisers create better outcomes for
                every client.
              </p>
            </div>
          </section>

          <section className="border-t border-slate-200/70 py-20 sm:py-24">
            <div className="mx-auto max-w-7xl px-6">
              <SectionHeading eyebrow="Testimonials" title="Built for the standard clients expect" />
              <div className="mt-12 grid gap-4 md:grid-cols-3">
                {[
                  ["KritiFin gives our team a clear morning view of what matters, before the inbox takes over.", "Principal Adviser"],
                  ["The meeting brief turns scattered notes into an executive summary we can actually use.", "Client Services Lead"],
                  ["It feels less like a chatbot and more like an operating rhythm for advice delivery.", "Managing Partner"],
                ].map(([quote, name]) => (
                  <figure key={quote} className="rounded-3xl border border-slate-200 bg-white p-6 shadow-xs">
                    <blockquote className="text-sm leading-6 text-slate-600">&quot;{quote}&quot;</blockquote>
                    <figcaption className="mt-5 text-sm font-semibold text-slate-950">{name}</figcaption>
                  </figure>
                ))}
              </div>
            </div>
          </section>

          <section id="faq" className="scroll-mt-20 border-t border-slate-200/70 bg-white py-20 sm:py-24">
            <div className="mx-auto max-w-3xl px-6">
              <SectionHeading eyebrow="FAQ" title="Frequently asked questions" />
              <div className="mt-10 divide-y divide-slate-200 overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xs">
                {FAQS.map((item) => (
                  <details key={item.q} className="group px-6 [&_summary]:list-none">
                    <summary className="flex cursor-pointer items-center justify-between gap-4 py-5 text-sm font-medium text-slate-950">
                      {item.q}
                      <ChevronRight
                        className="h-4 w-4 flex-shrink-0 text-slate-400 transition-transform group-open:rotate-90"
                        aria-hidden
                      />
                    </summary>
                    <p className="pb-5 text-sm leading-6 text-slate-500">{item.a}</p>
                  </details>
                ))}
              </div>
            </div>
          </section>

          <section className="border-t border-slate-200/70 py-20 sm:py-24">
            <div className="mx-auto max-w-4xl px-6 text-center">
              <h2 className="text-4xl font-semibold tracking-[-0.05em] text-slate-950 sm:text-5xl">
                Stay ahead of every client.
              </h2>
              <p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-slate-500">
                Give advisers a proactive workspace for reviews, follow-ups,
                client intelligence, and prepared action.
              </p>
              <div className="mt-8 flex flex-wrap justify-center gap-3">
                <ButtonLink
                  href={GET_STARTED_HREF}
                  size="lg"
                  leftIcon={<ArrowRight className="h-4 w-4" aria-hidden />}
                >
                  Start Free
                </ButtonLink>
                <ButtonLink href={ROUTES.login} variant="secondary" size="lg">
                  Book Demo
                </ButtonLink>
              </div>
            </div>
          </section>
        </main>

        <footer className="border-t border-slate-200 bg-white">
          <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-6 py-8 sm:flex-row">
            <BrandLogo size="sm" />
            <nav className="flex items-center gap-6" aria-label="Footer">
              <Link href={ROUTES.dashboard} className="text-sm text-slate-500 transition-colors hover:text-slate-950">
                Dashboard
              </Link>
              <Link href={ROUTES.chat} className="text-sm text-slate-500 transition-colors hover:text-slate-950">
                AI Copilot
              </Link>
              <a href="#capabilities" className="text-sm text-slate-500 transition-colors hover:text-slate-950">
                Capabilities
              </a>
            </nav>
            <p className="text-xs text-slate-500">
              (c) {new Date().getFullYear()} KritiFin. All rights reserved.
            </p>
          </div>
        </footer>
      </div>
    </>
  );
}
