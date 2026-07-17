import Head from "next/head";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { Bell, CheckCircle2, Clock, Database, FileText, Mail, Sparkles, Upload } from "lucide-react";
import AlertCard from "../components/AlertCard";
import DateSimulator from "../components/DateSimulator";
import { DemoSpotlight } from "../components/DemoSpotlight";
import LazyDraftEmailModal from "../components/LazyDraftEmailModal";
import {
  Card,
  CardHeader,
  Button,
  ButtonLink,
  Badge,
  EmptyState,
  ErrorState,
  DashboardSkeleton,
  PageIntro,
  PageShell,
  useToast,
} from "../components/ui";
import { useDraftEmailModalState } from "../hooks/useDraftEmailModalState";
import { usePageSetup } from "../hooks/usePageSetup";
import {
  usePulse,
  useCompleted,
  useLoadSampleData,
  useUpdateAlertStatus,
} from "../hooks/useApi";
import { errorMessage } from "../lib/api";
import { formatDate, todayISO } from "../lib/format";
import { alertTypeLabel, isReviewOverdue } from "../lib/labels";
import { briefForClient } from "../lib/routes";
import { chatWithQuery, DEMO_COPILOT_QUERY } from "../lib/demo";
import type { Alert, AlertType } from "../lib/types";

const DigestCard = dynamic(() => import("../components/DigestCard"), {
  loading: () => null,
});

/** Cap Pulse grid cards to keep DOM lean on large books. */
const PULSE_DISPLAY_LIMIT = 12;

/** Monday of the week containing d. */
function weekMonday(d: Date): Date {
  const mon = new Date(d);
  const day = mon.getDay();
  mon.setDate(mon.getDate() + (day === 0 ? -6 : 1 - day));
  return mon;
}

function alertsByWeek(alerts: Alert[], baseDateStr: string) {
  const base = new Date(baseDateStr + "T12:00:00");
  const end = new Date(base);
  end.setDate(end.getDate() + 30);
  const weekKeys = new Map<string, number>();
  let m = weekMonday(base);
  while (m <= end) {
    weekKeys.set(m.toISOString().slice(0, 10), 0);
    m.setDate(m.getDate() + 7);
  }
  for (const a of alerts) {
    const key = weekMonday(new Date(a.trigger_date + "T12:00:00"))
      .toISOString()
      .slice(0, 10);
    if (weekKeys.has(key)) weekKeys.set(key, (weekKeys.get(key) ?? 0) + 1);
  }
  return Array.from(weekKeys.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, count]) => {
      const start = new Date(key + "T12:00:00");
      const eow = new Date(start);
      eow.setDate(eow.getDate() + 6);
      const label = `${start.getDate()} ${start.toLocaleDateString("en-GB", { month: "short" })} – ${eow.getDate()} ${eow.toLocaleDateString("en-GB", { month: "short" })}`;
      return { weekLabel: label, count };
    });
}

function Kpi({
  label,
  value,
  hint,
  index = 0,
}: {
  label: string;
  value: number;
  hint?: string;
  index?: number;
}) {
  return (
    <Card
      className="animate-fade-in-up p-5 opacity-0 transition-shadow duration-200 hover:shadow-card"
      style={{ animationDelay: `${index * 60}ms`, animationFillMode: "forwards" }}
      data-testid={`kpi-card-${label.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <p className="ui-label">{label}</p>
      <p className="mt-2 text-kpi font-semibold tabular-nums text-slate-950">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </Card>
  );
}

const SETUP_STEPS = [
  {
    icon: <Upload className="h-4 w-4" aria-hidden />,
    title: "Upload documents",
    text: "Add client fact-finds and meeting notes — PDF or Word.",
  },
  {
    icon: <Sparkles className="h-4 w-4" aria-hidden />,
    title: "KritiFin extracts the signal",
    text: "Clients, review dates, deadlines and follow-ups are pulled out automatically.",
  },
  {
    icon: <Bell className="h-4 w-4" aria-hidden />,
    title: "Act on priorities",
    text: "See what's due, generate briefs, and draft emails in a click.",
  },
];

/** Premium first-run experience shown when the workspace has no data yet. */
function FirstRun() {
  const { notify } = useToast();
  const loadSample = useLoadSampleData();

  const handleLoadDemo = () => {
    loadSample.mutate(undefined, {
      onSuccess: (res) =>
        notify(
          res.loaded ? res.message : res.message || "Demo data already loaded.",
          res.loaded ? "success" : "info"
        ),
      onError: (e) => notify(errorMessage(e, "Couldn't load demo data."), "error"),
    });
  };

  return (
    <Card className="overflow-hidden animate-fade-in" data-testid="first-run-card">
      <div className="grid gap-px bg-slate-100 md:grid-cols-[1.1fr_1fr]">
        <div className="bg-white p-8 sm:p-10">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-xs">
            <Sparkles className="h-5 w-5" aria-hidden />
          </span>
          <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-brand-600">
            Getting started
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            Welcome to KritiFin
          </h2>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-slate-500">
            Upload client fact-finds or meeting notes and KritiFin will extract
            priorities, generate pre-meeting briefs, and draft follow-up emails — automatically.
            New here? Load a demo book to explore the product instantly.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="/admin" size="lg" leftIcon={<Upload className="h-4 w-4" aria-hidden />}>
              Upload your first document
            </ButtonLink>
            <Button
              variant="secondary"
              size="lg"
              onClick={handleLoadDemo}
              loading={loadSample.isPending}
              leftIcon={<Database className="h-4 w-4" aria-hidden />}
              data-testid="load-demo-data-button"
            >
              Load demo data
            </Button>
            <ButtonLink href="/chat" variant="ghost" leftIcon={<Sparkles className="h-4 w-4" aria-hidden />}>
              Explore AI Copilot
            </ButtonLink>
          </div>
        </div>
        <div className="bg-slate-50/80 p-8 sm:p-10">
          <p className="ui-label mb-5">How it works</p>
          <ol className="space-y-5">
            {SETUP_STEPS.map((step, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-white text-sm font-semibold text-brand-700 shadow-xs ring-1 ring-slate-200">
                  {i + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-950">{step.title}</p>
                  <p className="mt-0.5 text-sm leading-relaxed text-slate-500">{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Card>
  );
}

export default function Dashboard() {
  const [simulatedDate, setSimulatedDate] = useState(todayISO);
  const { source: draftEmailSource, openAlertDraft, closeDraft } = useDraftEmailModalState();

  const pulseQuery = usePulse(simulatedDate);
  const completedQuery = useCompleted();
  const updateStatus = useUpdateAlertStatus();

  const pulse = pulseQuery.data;
  const alerts = useMemo(() => pulse?.alerts ?? [], [pulse]);
  const overdueFollowUps = pulse?.overdue_follow_ups ?? [];
  const completedAlerts = completedQuery.data?.alerts ?? [];
  const pulseAlerts = useMemo(
    () => alerts.slice(0, PULSE_DISPLAY_LIMIT),
    [alerts]
  );
  const weeklyChart = useMemo(
    () => alertsByWeek(alerts, simulatedDate),
    [alerts, simulatedDate]
  );

  // True first run: no clients and no alerts at all — show onboarding, not a
  // grid of zeros (which reads as "broken" rather than "new").
  const hasNoData = !!pulse && pulse.total === 0 && pulse.client_count === 0;

  usePageSetup(
    "Dashboard",
    <>
      {alerts[0] && (
        <ButtonLink
          href={briefForClient(alerts[0].client_id)}
          leftIcon={<FileText className="h-4 w-4" aria-hidden />}
          data-testid="header-prepare-brief"
        >
          Prepare brief
        </ButtonLink>
      )}
      <DateSimulator value={simulatedDate} onChange={setSimulatedDate} />
    </>,
    [simulatedDate, alerts]
  );

  return (
    <>
      <Head>
        <title>Dashboard - KritiFin</title>
      </Head>

      {pulseQuery.isLoading && <DashboardSkeleton />}

      {pulseQuery.isError && (
        <PageShell wide>
          <ErrorState
            title="Couldn't load your dashboard"
            message={errorMessage(pulseQuery.error, "Couldn't load your dashboard.")}
            onRetry={() => pulseQuery.refetch()}
          />
        </PageShell>
      )}

      {pulse && !pulseQuery.isError && hasNoData && (
        <PageShell wide>
          <FirstRun />
        </PageShell>
      )}

      {pulse && !pulseQuery.isError && !hasNoData && (
        <PageShell wide>
          <div className="mb-8 animate-fade-in" data-testid="dashboard-hero">
            <p className="text-sm font-medium text-slate-500">Good Morning, James.</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-slate-950">
              Here&apos;s what deserves your attention today.
            </h2>
            <PageIntro className="mb-0 mt-3">
              Reviews, follow-ups, compliance items, and client intelligence in one proactive workspace.
            </PageIntro>
            {alerts[0] && (
              <div className="mt-6 flex flex-wrap gap-3">
                <ButtonLink
                  href={briefForClient(alerts[0].client_id)}
                  leftIcon={<FileText className="h-4 w-4" aria-hidden />}
                >
                  Prepare for next meeting
                </ButtonLink>
                <ButtonLink
                  href={chatWithQuery(DEMO_COPILOT_QUERY)}
                  variant="secondary"
                  leftIcon={<Sparkles className="h-4 w-4" aria-hidden />}
                >
                  Ask AI Copilot
                </ButtonLink>
              </div>
            )}
          </div>
          <DigestCard simulatedDate={simulatedDate} />
          {alerts[0] && (
            <DemoSpotlight alert={alerts[0]} onDraftEmail={openAlertDraft} />
          )}
          <div className="mb-8 grid grid-cols-2 gap-4 xl:grid-cols-5" data-testid="dashboard-kpis">
            <Kpi label="Reviews Due" value={pulse.total} hint="Open client priorities" index={0} />
            <Kpi label="Follow-ups" value={overdueFollowUps.length} hint="Past due commitments" index={1} />
            <Kpi label="Awaiting Response" value={pulse.high_risk} hint="High priority clients" index={2} />
            <Kpi label="Compliance Items" value={pulse.deadlines} hint="Upcoming deadlines" index={3} />
            <Kpi label="Documents Processed" value={pulse.client_count} hint="Active client records" index={4} />
          </div>

          {alerts.length > 0 ? (
            <Card className="mb-8 overflow-hidden" data-testid="priority-timeline">
              <div className="flex items-start gap-3 border-b border-slate-100 px-5 py-4 sm:px-6">
                <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                  <Sparkles className="h-4 w-4" aria-hidden />
                </span>
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">Priority Timeline</h2>
                  <p className="mt-0.5 text-sm text-slate-500">
                    The right client, insight, and action for the next 30 days.
                  </p>
                </div>
              </div>
              <ol className="divide-y divide-slate-100">
                {alerts.slice(0, 7).map((row, i) => (
                  <li
                    key={row.id}
                    className="flex items-center justify-between gap-4 px-5 py-3 sm:px-6"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold tabular-nums text-brand-700">
                        {i + 1}
                      </span>
                      <span className="truncate text-sm text-slate-700">
                        <strong className="font-medium text-slate-900">{row.client_name}</strong>
                        {" — "}
                        {isReviewOverdue(row.type) ? "Annual review overdue" : row.title || alertTypeLabel(row.type)}
                        {!isReviewOverdue(row.type) && row.trigger_date && (
                          <span className="ml-1 text-slate-500">· due {formatDate(row.trigger_date)}</span>
                        )}
                      </span>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <ButtonLink
                        href={briefForClient(row.client_id)}
                        size="sm"
                        variant="secondary"
                        data-testid={`prepare-brief-${row.id}`}
                      >
                        Prepare
                      </ButtonLink>
                      <Button size="sm" variant="secondary" onClick={() => openAlertDraft(row.id)}>
                        Draft email
                      </Button>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          ) : (
            <EmptyState
              className="mb-8"
              icon={<Upload className="h-5 w-5" aria-hidden />}
              title="No priorities yet"
              description="Upload client documents in Ingestion to extract alerts, or move the simulated date to see what's coming up."
              action={
                <ButtonLink href="/admin" leftIcon={<Upload className="h-4 w-4" aria-hidden />}>
                  Go to Ingestion
                </ButtonLink>
              }
            />
          )}

          {overdueFollowUps.length > 0 && (
            <Card className="mb-8 overflow-hidden">
              <div className="flex items-start gap-3 border-b border-slate-100 px-5 py-4 sm:px-6">
                <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
                  <Clock className="h-4 w-4" aria-hidden />
                </span>
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">Overdue follow-ups</h2>
                  <p className="mt-0.5 text-sm text-slate-500">
                    Follow-ups you committed to that are now past due.
                  </p>
                </div>
              </div>
              <ul className="divide-y divide-slate-100">
                {overdueFollowUps.map((row) => (
                  <li
                    key={row.id}
                    className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 sm:px-6"
                  >
                    <span className="min-w-0 text-sm text-slate-700">
                      <strong className="font-medium text-slate-900">{row.client_name}</strong>
                      {" — "}
                      {row.title || "Follow-up"}
                      {row.trigger_date && (
                        <span className="ml-1 text-amber-700">· was due {formatDate(row.trigger_date)}</span>
                      )}
                    </span>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        size="sm"
                        leftIcon={<Mail className="h-4 w-4" aria-hidden />}
                        onClick={() => openAlertDraft(row.id)}
                      >
                        Draft email
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={updateStatus.isPending && updateStatus.variables?.alertId === row.id}
                        onClick={() => updateStatus.mutate({ alertId: row.id, status: "COMPLETED" })}
                      >
                        Mark done
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {alerts.length > 0 && (
            <div className="mb-10 grid gap-4 lg:grid-cols-3" data-testid="dashboard-recommendations">
              <Card className="border-ai-100 bg-ai-50/40 p-5 lg:col-span-2">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-ai-600" aria-hidden />
                  <h2 className="text-sm font-semibold text-slate-950">Suggested next actions</h2>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  {alerts.slice(0, 2).map((row) => (
                    <div key={row.id} className="rounded-2xl border border-white bg-white/85 p-4 shadow-xs">
                      <p className="text-sm font-semibold text-slate-950">{row.client_name}</p>
                      <p className="mt-2 text-sm leading-6 text-slate-600">
                        {row.description || row.title || "Review this client and confirm the next best action."}
                      </p>
                      <Button
                        size="sm"
                        variant="secondary"
                        className="mt-4"
                        onClick={() => openAlertDraft(row.id)}
                      >
                        Draft next action
                      </Button>
                    </div>
                  ))}
                </div>
              </Card>
              <Card className="p-5">
                <h2 className="text-sm font-semibold text-slate-950">Upcoming Meetings</h2>
                <div className="mt-5 space-y-4">
                  {alerts.slice(0, 3).map((row) => (
                    <div key={row.id} className="flex gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full bg-brand-600" />
                      <div>
                        <p className="text-sm font-medium text-slate-950">{row.client_name}</p>
                        <p className="text-xs text-slate-500">{formatDate(row.trigger_date)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          )}

          {alerts.length > 0 && (
            <details className="mb-10 group">
              <summary className="cursor-pointer list-none text-sm font-medium text-brand-600 hover:text-brand-700 [&::-webkit-details-marker]:hidden">
                Show all alert cards ({Math.min(alerts.length, PULSE_DISPLAY_LIMIT)} of {alerts.length}) →
              </summary>
              <div className="mt-4">
                <div className="mb-4 flex items-center justify-between">
                  <h2 className="text-base font-semibold text-slate-900">Pulse</h2>
                  <Link href="/alerts" className="text-sm font-medium text-brand-600 hover:text-brand-700">
                    View all alerts →
                  </Link>
                </div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {pulseAlerts.map((row) => (
                    <AlertCard
                      key={row.id}
                      type={row.type as AlertType}
                      priority={row.priority as "HIGH" | "MEDIUM" | "LOW"}
                      title={row.title || "Alert"}
                      description={row.description || ""}
                      clientName={row.client_name}
                      prepareHref={briefForClient(row.client_id)}
                      draftAlertId={row.id}
                      onDraftAlert={openAlertDraft}
                    />
                  ))}
                </div>
                {alerts.length > PULSE_DISPLAY_LIMIT && (
                  <p className="mt-4 text-center text-sm text-slate-500">
                    Showing {PULSE_DISPLAY_LIMIT} of {alerts.length} alerts.{" "}
                    <Link href="/alerts" className="font-medium text-brand-600 hover:text-brand-700">
                      View all →
                    </Link>
                  </p>
                )}
              </div>
            </details>
          )}

          {alerts.length > 0 && (
            <details className="mb-10 group">
              <summary className="cursor-pointer list-none text-sm font-medium text-slate-500 hover:text-slate-700 [&::-webkit-details-marker]:hidden">
                More insights (timeline chart & completed alerts) →
              </summary>
              <div className="mt-4 space-y-10">
                <Card className="overflow-hidden">
                  <CardHeader
                    title="Alerts over time"
                    description="Weekly count of alerts in the next 30 days from your selected date."
                  />
                  {(() => {
                    const byWeek = weeklyChart;
                    const maxCount = Math.max(1, ...byWeek.map((w) => w.count));
                    return (
                      <table className="w-full text-sm">
                        <tbody>
                          {byWeek.map(({ weekLabel, count }) => (
                            <tr key={weekLabel} className="border-b border-slate-50 last:border-0">
                              <td className="w-40 px-5 py-3 text-slate-600 sm:px-6">{weekLabel}</td>
                              <td className="px-2 py-3">
                                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                                  <div
                                    className="h-full rounded-full bg-brand-500 transition-all"
                                    style={{ width: `${(count / maxCount) * 100}%`, minWidth: count > 0 ? 4 : 0 }}
                                  />
                                </div>
                              </td>
                              <td className="w-12 px-5 py-3 text-right font-semibold tabular-nums text-slate-900 sm:px-6">{count}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    );
                  })()}
                </Card>

                <Card className="overflow-hidden">
                  <CardHeader title="Recently completed" description="Alerts you marked as done." />
                  {completedQuery.isError ? (
                    <div className="px-6 py-4">
                      <ErrorState
                        compact
                        message="Couldn't load completed alerts."
                        onRetry={() => completedQuery.refetch()}
                      />
                    </div>
                  ) : completedAlerts.length > 0 ? (
                    <ul className="divide-y divide-slate-100">
                      {completedAlerts.map((row) => (
                        <li key={row.id} className="flex flex-wrap items-center gap-3 px-6 py-4">
                          <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-emerald-500" aria-hidden />
                          <span className="flex-1 text-sm font-medium text-slate-700">{row.client_name}</span>
                          <span className="text-xs text-slate-500">{alertTypeLabel(row.type)}</span>
                          <span className="text-xs text-slate-500">{formatDate(row.trigger_date)}</span>
                          <Badge className="bg-emerald-100 text-emerald-700">Done</Badge>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <EmptyState
                      icon={<CheckCircle2 className="h-5 w-5" aria-hidden />}
                      title="Nothing completed yet"
                      description="Use Draft email on an alert, then Mark as done to see it here."
                    />
                  )}
                </Card>
              </div>
            </details>
          )}
        </PageShell>
      )}

      {draftEmailSource && (
        <LazyDraftEmailModal
          source={draftEmailSource}
          onClose={closeDraft}
          onMarkDone={closeDraft}
        />
      )}
    </>
  );
}
