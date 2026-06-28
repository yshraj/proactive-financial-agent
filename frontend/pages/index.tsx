import Head from "next/head";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Bell, CheckCircle2, Clock, Mail, Sparkles, Upload } from "lucide-react";
import AlertCard from "../components/AlertCard";
import DateSimulator from "../components/DateSimulator";
import DraftEmailModal from "../components/DraftEmailModal";
import { useLayout } from "../contexts/LayoutContext";
import {
  Card,
  CardHeader,
  Button,
  Badge,
  EmptyState,
  ErrorState,
  DashboardSkeleton,
} from "../components/ui";
import { usePulse, useCompleted, useUpdateAlertStatus } from "../hooks/useApi";
import { formatDate, todayISO } from "../lib/format";
import { alertTypeLabel, isReviewOverdue } from "../lib/labels";
import type { Alert, AlertType } from "../lib/types";

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

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <Card className="p-5 transition-shadow hover:shadow-card-hover">
      <p className="overline">{label}</p>
      <p className="mt-2 text-kpi font-semibold tabular-nums text-gray-900">{value}</p>
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
    title: "Jarvis extracts the signal",
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
  return (
    <Card className="overflow-hidden">
      <div className="grid gap-px bg-gray-100 md:grid-cols-[1.1fr_1fr]">
        <div className="bg-white p-8 sm:p-10">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-white shadow-xs">
            <Sparkles className="h-5 w-5" aria-hidden />
          </span>
          <h2 className="mt-5 text-xl font-semibold tracking-tight text-gray-900">
            Welcome to Jarvis
          </h2>
          <p className="mt-2 max-w-md text-sm leading-relaxed text-gray-500">
            Your proactive layer for client work. Upload a few documents and Jarvis
            turns them into priorities, pre-meeting briefs, and ready-to-send emails.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link href="/admin">
              <Button leftIcon={<Upload className="h-4 w-4" aria-hidden />}>
                Upload documents
              </Button>
            </Link>
            <Link href="/chat">
              <Button variant="secondary" leftIcon={<Sparkles className="h-4 w-4" aria-hidden />}>
                Ask Jarvis
              </Button>
            </Link>
          </div>
        </div>
        <div className="bg-gray-50/60 p-8 sm:p-10">
          <p className="overline mb-4">How it works</p>
          <ol className="space-y-5">
            {SETUP_STEPS.map((step, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-white text-brand-600 shadow-xs ring-1 ring-gray-100">
                  {step.icon}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900">{step.title}</p>
                  <p className="mt-0.5 text-sm text-gray-500">{step.text}</p>
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
  const { setPageTitle, setHeaderExtra } = useLayout();
  const [simulatedDate, setSimulatedDate] = useState(todayISO);
  const [draftEmailAlertId, setDraftEmailAlertId] = useState<string | null>(null);

  const pulseQuery = usePulse(simulatedDate);
  const completedQuery = useCompleted();
  const updateStatus = useUpdateAlertStatus();

  const pulse = pulseQuery.data;
  const alerts = pulse?.alerts ?? [];
  const overdueFollowUps = pulse?.overdue_follow_ups ?? [];
  const completedAlerts = completedQuery.data?.alerts ?? [];

  // True first run: no clients and no alerts at all — show onboarding, not a
  // grid of zeros (which reads as "broken" rather than "new").
  const hasNoData = !!pulse && pulse.total === 0 && pulse.client_count === 0;

  useEffect(() => {
    setPageTitle("Dashboard");
    setHeaderExtra(
      <>
        <Link
          href="/chat"
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white shadow-xs transition-colors hover:bg-brand-500"
        >
          <Sparkles className="h-4 w-4" aria-hidden />
          Ask Jarvis
        </Link>
        <DateSimulator value={simulatedDate} onChange={setSimulatedDate} />
      </>
    );
    return () => setHeaderExtra(null);
  }, [setPageTitle, setHeaderExtra, simulatedDate]);

  return (
    <>
      <Head>
        <title>Dashboard — Jarvis</title>
      </Head>

      {pulseQuery.isLoading && <DashboardSkeleton />}

      {pulseQuery.isError && (
        <ErrorState
          title="Couldn't load your dashboard"
          message={(pulseQuery.error as Error)?.message}
          onRetry={() => pulseQuery.refetch()}
        />
      )}

      {pulse && !pulseQuery.isError && hasNoData && <FirstRun />}

      {pulse && !pulseQuery.isError && !hasNoData && (
        <>
          <p className="mb-8 max-w-2xl text-sm leading-relaxed text-gray-500">
            What&apos;s due, pre-meeting briefs, and draft emails — in one place.
          </p>
          <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi label="Total alerts" value={pulse.total} />
            <Kpi label="High risk" value={pulse.high_risk} />
            <Kpi label="Upcoming deadlines" value={pulse.deadlines} />
            <Kpi label="Clients" value={pulse.client_count} />
          </div>

          {alerts.length > 0 ? (
            <Card className="mb-8 overflow-hidden">
              <div className="flex items-start gap-3 border-b border-gray-100 px-5 py-4 sm:px-6">
                <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                  <Sparkles className="h-4 w-4" aria-hidden />
                </span>
                <div>
                  <h2 className="text-sm font-semibold text-gray-900">Start here</h2>
                  <p className="mt-0.5 text-sm text-gray-500">
                    Your top priorities for the next 30 days.
                  </p>
                </div>
              </div>
              <ol className="divide-y divide-gray-100">
                {alerts.slice(0, 7).map((row, i) => (
                  <li
                    key={row.id}
                    className="flex items-center justify-between gap-4 px-5 py-3 sm:px-6"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold tabular-nums text-brand-700">
                        {i + 1}
                      </span>
                      <span className="truncate text-sm text-gray-700">
                        <strong className="font-medium text-gray-900">{row.client_name}</strong>
                        {" — "}
                        {isReviewOverdue(row.type) ? "Annual review overdue" : row.title || alertTypeLabel(row.type)}
                        {!isReviewOverdue(row.type) && row.trigger_date && (
                          <span className="ml-1 text-gray-400">· due {formatDate(row.trigger_date)}</span>
                        )}
                      </span>
                    </div>
                    <Button size="sm" variant="secondary" className="shrink-0" onClick={() => setDraftEmailAlertId(row.id)}>
                      Draft email
                    </Button>
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
                <Link href="/admin">
                  <Button leftIcon={<Upload className="h-4 w-4" aria-hidden />}>Go to Ingestion</Button>
                </Link>
              }
            />
          )}

          {overdueFollowUps.length > 0 && (
            <Card className="mb-8 overflow-hidden">
              <div className="flex items-start gap-3 border-b border-gray-100 px-5 py-4 sm:px-6">
                <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
                  <Clock className="h-4 w-4" aria-hidden />
                </span>
                <div>
                  <h2 className="text-sm font-semibold text-gray-900">Overdue follow-ups</h2>
                  <p className="mt-0.5 text-sm text-gray-500">
                    Follow-ups you committed to that are now past due.
                  </p>
                </div>
              </div>
              <ul className="divide-y divide-gray-100">
                {overdueFollowUps.map((row) => (
                  <li
                    key={row.id}
                    className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 sm:px-6"
                  >
                    <span className="min-w-0 text-sm text-gray-700">
                      <strong className="font-medium text-gray-900">{row.client_name}</strong>
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
                        onClick={() => setDraftEmailAlertId(row.id)}
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
            <div className="mb-10">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-base font-semibold text-gray-900">Pulse</h2>
                <Link href="/alerts" className="text-sm font-medium text-brand-600 hover:text-brand-700">
                  View all alerts →
                </Link>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {alerts.map((row) => (
                  <AlertCard
                    key={row.id}
                    type={row.type as AlertType}
                    priority={row.priority as "HIGH" | "MEDIUM" | "LOW"}
                    title={row.title || "Alert"}
                    description={row.description || ""}
                    clientName={row.client_name}
                    onDraftEmail={() => setDraftEmailAlertId(row.id)}
                  />
                ))}
              </div>
            </div>
          )}

          {alerts.length > 0 && (
            <Card className="mb-10 overflow-hidden">
              <CardHeader
                title="Alerts over time"
                description="Weekly count of alerts in the next 30 days from your selected date."
              />
              {(() => {
                const byWeek = alertsByWeek(alerts, simulatedDate);
                const maxCount = Math.max(1, ...byWeek.map((w) => w.count));
                return (
                  <table className="w-full text-sm">
                    <tbody>
                      {byWeek.map(({ weekLabel, count }) => (
                        <tr key={weekLabel} className="border-b border-gray-50 last:border-0">
                          <td className="w-40 px-5 py-3 text-gray-600 sm:px-6">{weekLabel}</td>
                          <td className="px-2 py-3">
                            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                              <div
                                className="h-full rounded-full bg-brand-500 transition-all"
                                style={{ width: `${(count / maxCount) * 100}%`, minWidth: count > 0 ? 4 : 0 }}
                              />
                            </div>
                          </td>
                          <td className="w-12 px-5 py-3 text-right font-semibold tabular-nums text-gray-900 sm:px-6">{count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                );
              })()}
            </Card>
          )}

          <Card className="overflow-hidden">
            <CardHeader title="Recently completed" description="Alerts you marked as done." />
            {completedAlerts.length > 0 ? (
              <ul className="divide-y divide-gray-100">
                {completedAlerts.map((row) => (
                  <li key={row.id} className="flex flex-wrap items-center gap-3 px-6 py-4">
                    <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-emerald-500" aria-hidden />
                    <span className="flex-1 text-sm font-medium text-gray-700">{row.client_name}</span>
                    <span className="text-xs text-gray-500">{alertTypeLabel(row.type)}</span>
                    <span className="text-xs text-gray-500">{formatDate(row.trigger_date)}</span>
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
        </>
      )}

      <DraftEmailModal
        alertId={draftEmailAlertId}
        onClose={() => setDraftEmailAlertId(null)}
        onMarkDone={() => {
          setDraftEmailAlertId(null);
          pulseQuery.refetch();
          completedQuery.refetch();
        }}
      />
    </>
  );
}
