import Head from "next/head";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Bell, CheckCircle2, Mail, Sparkles, Upload } from "lucide-react";
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

function Kpi({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <Card className={`bg-gradient-to-br p-6 transition-shadow hover:shadow-card-hover ${tone}`}>
      <p className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">{label}</p>
      <p className="text-kpi font-bold tracking-tight text-gray-900">{value}</p>
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

  useEffect(() => {
    setPageTitle("Dashboard");
    setHeaderExtra(
      <>
        <Link
          href="/chat"
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-500"
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

      <p className="mb-1 text-sm font-medium text-gray-700">
        Your proactive layer: see what&apos;s due, get briefs, and draft emails in one place.
      </p>
      <p className="mb-6 text-sm leading-relaxed text-gray-500">
        Overview of alerts and activity for the selected date range. Use the date picker in the header to simulate a future date.
      </p>

      {pulseQuery.isLoading && <DashboardSkeleton />}

      {pulseQuery.isError && (
        <ErrorState
          title="Couldn't load your dashboard"
          message={(pulseQuery.error as Error)?.message}
          onRetry={() => pulseQuery.refetch()}
        />
      )}

      {pulse && !pulseQuery.isError && (
        <>
          <div className="mb-8 grid grid-cols-2 gap-4 sm:gap-6 lg:grid-cols-4">
            <Kpi label="Total alerts" value={pulse.total} tone="from-white to-gray-50/80" />
            <Kpi label="High risk" value={pulse.high_risk} tone="from-white to-red-50/30" />
            <Kpi label="Upcoming deadlines" value={pulse.deadlines} tone="from-white to-amber-50/40" />
            <Kpi label="Clients" value={pulse.client_count} tone="from-white to-brand-50/40" />
          </div>

          {alerts.length > 0 ? (
            <Card className="mb-8 border-brand-100 bg-brand-50/40 p-6">
              <h2 className="mb-1 text-sm font-semibold text-brand-900">Start here</h2>
              <p className="mb-4 text-xs text-brand-700/90">
                Your top priorities for the next 30 days. Tackle these first.
              </p>
              <ol className="space-y-2">
                {alerts.slice(0, 7).map((row, i) => (
                  <li key={row.id} className="flex items-center justify-between gap-4 text-sm">
                    <span className="text-gray-800">
                      <strong className="text-gray-900">
                        {i + 1}. {row.client_name}
                      </strong>
                      {" – "}
                      {isReviewOverdue(row.type) ? "Annual review overdue" : row.title || alertTypeLabel(row.type)}
                      {!isReviewOverdue(row.type) && row.trigger_date && (
                        <span className="ml-1 text-gray-500">(due {formatDate(row.trigger_date)})</span>
                      )}
                    </span>
                    <Button size="sm" className="shrink-0" onClick={() => setDraftEmailAlertId(row.id)}>
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
            <Card className="mb-8 border-amber-200 bg-amber-50/50 p-6">
              <h2 className="mb-1 text-sm font-semibold text-amber-900">Overdue follow-ups</h2>
              <p className="mb-4 text-xs text-amber-800/90">
                Follow-ups you committed to that are now past due. Chase these with the client.
              </p>
              <ul className="space-y-2">
                {overdueFollowUps.map((row) => (
                  <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 text-sm">
                    <span className="text-gray-800">
                      <strong className="text-gray-900">{row.client_name}</strong>
                      {" – "}
                      {row.title || "Follow-up"}
                      {row.trigger_date && (
                        <span className="ml-1 text-gray-500">(was due {formatDate(row.trigger_date)})</span>
                      )}
                    </span>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        size="sm"
                        className="bg-amber-600 hover:bg-amber-500"
                        leftIcon={<Mail className="h-4 w-4" aria-hidden />}
                        onClick={() => setDraftEmailAlertId(row.id)}
                      >
                        Draft email
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        className="border-amber-300 text-amber-700 hover:bg-amber-50"
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
              <div className="bg-gray-50/50 px-6 py-6">
                {(() => {
                  const byWeek = alertsByWeek(alerts, simulatedDate);
                  const maxCount = Math.max(1, ...byWeek.map((w) => w.count));
                  return (
                    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-100 bg-gray-50/80">
                            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Week</th>
                            <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Alerts</th>
                            <th className="w-32 px-4 py-3"> </th>
                          </tr>
                        </thead>
                        <tbody>
                          {byWeek.map(({ weekLabel, count }) => (
                            <tr key={weekLabel} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
                              <td className="px-4 py-3 text-gray-700">{weekLabel}</td>
                              <td className="px-4 py-3 text-right font-semibold tabular-nums text-gray-900">{count}</td>
                              <td className="px-4 py-2">
                                <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                                  <div
                                    className="h-full rounded-full bg-brand-500"
                                    style={{ width: `${(count / maxCount) * 100}%`, minWidth: count > 0 ? 4 : 0 }}
                                  />
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}
              </div>
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
