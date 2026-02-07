import Head from "next/head";
import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import AlertCard from "../components/AlertCard";
import DateSimulator from "../components/DateSimulator";
import DraftEmailModal from "../components/DraftEmailModal";
import { useLayout } from "../contexts/LayoutContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatDate(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** Monday of the week containing d (ISO weekday: Mon=1). */
function weekMonday(d: Date): Date {
  const mon = new Date(d);
  const day = mon.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  mon.setDate(mon.getDate() + diff);
  return mon;
}

/** Group alerts by week (Monday–Sunday). Returns { weekLabel, count }[] for weeks in the 30-day window. */
function alertsByWeek(alerts: AlertRow[], baseDateStr: string): { weekLabel: string; count: number }[] {
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
    const d = new Date(a.trigger_date + "T12:00:00");
    const key = weekMonday(d).toISOString().slice(0, 10);
    if (weekKeys.has(key)) weekKeys.set(key, (weekKeys.get(key) ?? 0) + 1);
  }
  const sorted = Array.from(weekKeys.entries()).sort(([a], [b]) => a.localeCompare(b));
  return sorted.map(([key, count]) => {
    const start = new Date(key + "T12:00:00");
    const endOfWeek = new Date(start);
    endOfWeek.setDate(endOfWeek.getDate() + 6);
    const weekLabel = `${start.getDate()} ${start.toLocaleDateString("en-GB", { month: "short" })} – ${endOfWeek.getDate()} ${endOfWeek.toLocaleDateString("en-GB", { month: "short" })}`;
    return { weekLabel, count };
  });
}

type AlertRow = {
  id: string;
  client_id: string;
  client_name: string;
  trigger_date: string;
  type: string;
  priority: string;
  title: string | null;
  description: string | null;
  status: string;
};

type PulseData = {
  alerts: AlertRow[];
  total: number;
  high_risk: number;
  deadlines: number;
  client_count: number;
  overdue_follow_ups?: AlertRow[];
};

export default function Dashboard() {
  const { setPageTitle, setHeaderExtra } = useLayout();
  const [simulatedDate, setSimulatedDate] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  });
  const [pulse, setPulse] = useState<PulseData | null>(null);
  const [completedAlerts, setCompletedAlerts] = useState<AlertRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draftEmailAlertId, setDraftEmailAlertId] = useState<string | null>(null);

  const fetchPulse = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/monitor/pulse?simulated_date=${simulatedDate}`);
      if (!res.ok) throw new Error(res.status === 404 ? "Monitor API not found" : `Failed: ${res.status}`);
      const data = await res.json();
      setPulse(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
      setPulse(null);
    } finally {
      setLoading(false);
    }
  }, [simulatedDate]);

  const fetchCompleted = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/monitor/completed?limit=10`);
      const data = await res.json().catch(() => ({}));
      if (res.ok && Array.isArray(data.alerts)) {
        setCompletedAlerts(data.alerts);
      } else {
        setCompletedAlerts([]);
      }
    } catch {
      setCompletedAlerts([]);
    }
  }, []);

  useEffect(() => {
    fetchPulse();
  }, [fetchPulse]);

  useEffect(() => {
    fetchCompleted();
  }, [fetchCompleted]);

  useEffect(() => {
    setPageTitle("Dashboard");
    setHeaderExtra(
      <div className="flex items-end justify-end gap-4">
        <Link
          href="/chat"
          className="inline-flex h-10 items-center rounded-lg bg-sky-600 px-4 text-sm font-medium text-white shadow-sm transition-colors hover:bg-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2"
          title="Open chat with Jarvis to ask questions about your clients and documents"
        >
          Ask Jarvis
        </Link>
        <DateSimulator value={simulatedDate} onChange={setSimulatedDate} />
      </div>
    );
    return () => setHeaderExtra(null);
  }, [setPageTitle, setHeaderExtra, simulatedDate]);

  const alerts = pulse?.alerts ?? [];
  const overdueFollowUps = pulse?.overdue_follow_ups ?? [];
  const total = pulse?.total ?? 0;
  const highRiskCount = pulse?.high_risk ?? 0;
  const deadlinesCount = pulse?.deadlines ?? 0;
  const clientCount = pulse?.client_count ?? 0;

  return (
    <>
      <Head>
        <title>Dashboard – Jarvis</title>
      </Head>

      <p className="mb-2 text-sm font-medium text-gray-700">
        Your proactive layer: see what’s due, get briefs, and draft emails in one place.
      </p>
      <p className="mb-6 text-sm leading-relaxed text-gray-500">
        Overview of alerts and activity for the selected date range. Use the date picker in the header to simulate a future date.
      </p>

      {alerts.length > 0 ? (
        <div className="mb-8 rounded-xl border border-sky-100 bg-sky-50/50 px-6 py-5">
          <h2 className="mb-3 text-sm font-semibold text-sky-900">Start here</h2>
          <p className="mb-4 text-xs text-sky-700/90">Your top priorities for the next 30 days. Tackle these first.</p>
          <ol className="space-y-2">
            {alerts
              .slice(0, 7)
              .map((row, i) => (
                <li key={row.id} className="flex items-center justify-between gap-4 text-sm">
                  <span className="text-gray-800">
                    <strong className="text-gray-900">{i + 1}. {row.client_name}</strong>
                    {" – "}
                    {row.type === "REVIEW_OVERDUE" ? "Annual review overdue" : (row.title || row.type)}
                    {row.type !== "REVIEW_OVERDUE" && row.trigger_date && (
                      <span className="ml-1 text-gray-500">
                        (due {formatDate(row.trigger_date)})
                      </span>
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => setDraftEmailAlertId(row.id)}
                    className="shrink-0 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
                  >
                    Draft email
                  </button>
                </li>
              ))}
          </ol>
        </div>
      ) : (
        <div className="mb-8 rounded-xl border border-gray-200 bg-gray-50/50 px-6 py-5">
          <h2 className="mb-2 text-sm font-semibold text-gray-700">Start here</h2>
          <p className="text-sm text-gray-500">
            No priorities yet. Upload documents in <strong>Ingestion</strong> or run the seed script to see alerts here.
          </p>
        </div>
      )}

      {overdueFollowUps.length > 0 && (
        <div className="mb-8 rounded-xl border border-amber-200 bg-amber-50/50 px-6 py-5">
          <h2 className="mb-3 text-sm font-semibold text-amber-900">Overdue follow-ups</h2>
          <p className="mb-4 text-xs text-amber-800/90">Follow-ups you committed to that are now past due. Chase these with the client.</p>
          <ul className="space-y-2">
            {overdueFollowUps.map((row) => (
              <li key={row.id} className="flex items-center justify-between gap-4 text-sm">
                <span className="text-gray-800">
                  <strong className="text-gray-900">{row.client_name}</strong>
                  {" – "}
                  {row.title || "Follow-up"}
                  {row.trigger_date && (
                    <span className="ml-1 text-gray-500">(was due {formatDate(row.trigger_date)})</span>
                  )}
                </span>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    onClick={() => setDraftEmailAlertId(row.id)}
                    className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-500"
                  >
                    Draft email
                  </button>
                  {!row.id.startsWith("review-overdue-") && (
                    <button
                      type="button"
                      onClick={() => {
                        fetch(`${API_BASE}/api/monitor/alerts/${row.id}/status`, {
                          method: "PATCH",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ status: "COMPLETED" }),
                        }).then(() => fetchPulse());
                      }}
                      className="rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50"
                    >
                      Mark done
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && (
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
          {error}. Ensure the backend is running and the monitor API is available.
        </div>
      )}

      {loading && !pulse && (
        <p className="mb-6 text-sm text-gray-500">Loading dashboard…</p>
      )}

      <div className="mb-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <div
          className="group relative rounded-xl border border-gray-200 bg-gradient-to-br from-white to-gray-50/80 p-6 shadow-card transition-shadow hover:shadow-card-hover"
          title="Alerts due in the next 30 days from your selected date (including review-overdue)"
        >
          <p className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">Total alerts</p>
          <p className="text-kpi font-bold tracking-tight text-gray-900">{total}</p>
          <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-56 -translate-x-1/2 rounded-lg bg-gray-900 px-3 py-2 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
            Alerts due in the next 30 days from your selected date (including review-overdue clients).
            <span className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
          </div>
        </div>
        <div
          className="group relative rounded-xl border border-gray-200 bg-gradient-to-br from-white to-red-50/30 p-6 shadow-card transition-shadow hover:shadow-card-hover"
          title="Alerts marked as high priority"
        >
          <p className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">High risk</p>
          <p className="text-kpi font-bold tracking-tight text-gray-900">{highRiskCount}</p>
          <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-56 -translate-x-1/2 rounded-lg bg-gray-900 px-3 py-2 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
            Alerts marked as high priority. Tackle these first for compliance and client care.
            <span className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
          </div>
        </div>
        <div
          className="group relative rounded-xl border border-gray-200 bg-gradient-to-br from-white to-amber-50/40 p-6 shadow-card transition-shadow hover:shadow-card-hover"
          title="Alerts that are deadlines (e.g. policy expiry, review due)"
        >
          <p className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">Upcoming deadlines</p>
          <p className="text-kpi font-bold tracking-tight text-gray-900">{deadlinesCount}</p>
          <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-56 -translate-x-1/2 rounded-lg bg-gray-900 px-3 py-2 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
            Alerts that are deadlines (e.g. policy expiry, review due) in your date window.
            <span className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
          </div>
        </div>
        <div
          className="group relative rounded-xl border border-gray-200 bg-gradient-to-br from-white to-sky-50/40 p-6 shadow-card transition-shadow hover:shadow-card-hover"
          title="Total number of clients in your book"
        >
          <p className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">Clients</p>
          <p className="text-kpi font-bold tracking-tight text-gray-900">{clientCount}</p>
          <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-56 -translate-x-1/2 rounded-lg bg-gray-900 px-3 py-2 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
            Total number of clients in your book. Populated from ingested documents.
            <span className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
          </div>
        </div>
      </div>

      {alerts.length > 0 && (
        <div className="mb-10">
          <h2 className="mb-4 text-base font-semibold text-gray-900">Pulse</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {alerts.map((row) => (
              <AlertCard
                key={row.id}
                type={row.type as "DEADLINE" | "OPPORTUNITY" | "COMPLIANCE" | "REVIEW_OVERDUE" | "FOLLOW_UP"}
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

      <div className="mb-10 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card">
        <div className="border-b border-gray-100 px-6 py-5">
          <h2 className="text-base font-semibold text-gray-900">Alerts over time</h2>
          <p className="mt-1 text-sm text-gray-500">
            Weekly count of alerts in the next 30 days from your selected date.
          </p>
        </div>
        <div className="bg-gray-50/50 px-6 py-6 sm:px-8 sm:py-8">
          {pulse && alerts.length > 0 ? (
            (() => {
              const byWeek = alertsByWeek(alerts, simulatedDate);
              const maxCount = Math.max(1, ...byWeek.map((w) => w.count));
              const peakCount = Math.max(...byWeek.map((w) => w.count));
              const peakWeek = byWeek.find((w) => w.count === peakCount);
              return (
                <div className="flex flex-col gap-6">
                  <p className="text-sm font-medium text-gray-700">
                    <span className="tabular-nums">{alerts.length}</span> total alert{alerts.length !== 1 ? "s" : ""} from {simulatedDate}
                    {peakCount > 0 && peakWeek && (
                      <span className="ml-2 text-gray-500">· Peak: <span className="font-semibold text-sky-700">{peakCount}</span> in week of {peakWeek.weekLabel.split(" – ")[0]}</span>
                    )}
                  </p>

                  <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-100 bg-gray-50/80">
                          <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Week</th>
                          <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Alerts</th>
                          <th className="w-32 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500"> </th>
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
                                  className="h-full rounded-full bg-sky-500"
                                  style={{ width: `${(count / maxCount) * 100}%`, minWidth: count > 0 ? 4 : 0 }}
                                  title={`${count} alert${count !== 1 ? "s" : ""}`}
                                />
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })()
          ) : (
            <p className="flex h-32 items-center justify-center text-sm text-gray-500">
              No alerts in this date range. Upload documents in Ingestion or run the seed script to populate data.
            </p>
          )}
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card">
        <div className="border-b border-gray-100 px-6 py-5">
          <h2 className="text-base font-semibold text-gray-900">Recent alerts</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Client</th>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Type</th>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Risk</th>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Due date</th>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
                <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Action</th>
              </tr>
            </thead>
            <tbody>
              {alerts.length === 0 && !loading && (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                    No alerts in the selected window. Try a different date, upload documents in Ingestion, or run the seed script.
                  </td>
                </tr>
              )}
              {alerts.map((row) => (
                <tr key={row.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
                  <td className="px-6 py-4 font-medium text-gray-900">{row.client_name}</td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${
                        row.type === "DEADLINE"
                          ? "bg-amber-100 text-amber-800"
                          : row.type === "OPPORTUNITY"
                            ? "bg-emerald-100 text-emerald-800"
                            : row.type === "FOLLOW_UP"
                              ? "bg-slate-100 text-slate-700"
                              : row.type === "REVIEW_OVERDUE"
                                ? "bg-red-100 text-red-700"
                                : "bg-indigo-100 text-indigo-800"
                      }`}
                    >
                      {row.type === "FOLLOW_UP" ? "Waiting on client" : row.type === "REVIEW_OVERDUE" ? "Review overdue" : row.type}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${
                        row.priority === "HIGH"
                          ? "bg-red-100 text-red-700"
                          : row.priority === "MEDIUM"
                            ? "bg-sky-100 text-sky-700"
                            : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {row.priority}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-gray-600">{formatDate(row.trigger_date)}</td>
                  <td className="px-6 py-4 text-gray-500">{row.status}</td>
                  <td className="px-6 py-4 text-right">
                    <button
                      type="button"
                      onClick={() => setDraftEmailAlertId(row.id)}
                      className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
                    >
                      Draft Email
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-10 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card">
        <div className="border-b border-gray-100 px-6 py-5">
          <h2 className="text-base font-semibold text-gray-900">Recently completed</h2>
          <p className="mt-1 text-sm text-gray-500">Alerts you marked as done (read-only; no draft email).</p>
        </div>
        {completedAlerts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Client</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Type</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Due date</th>
                  <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
                </tr>
              </thead>
              <tbody>
                {completedAlerts.map((row) => (
                  <tr key={row.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
                    <td className="px-6 py-4 font-medium text-gray-700">{row.client_name}</td>
                    <td className="px-6 py-4">
                      <span className="inline-flex rounded-md px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-700">{row.type}</span>
                    </td>
                    <td className="px-6 py-4 text-gray-600">{formatDate(row.trigger_date)}</td>
                    <td className="px-6 py-4">
                      <span className="inline-flex rounded-md px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700">Done</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-6 py-8 text-center text-sm text-gray-500">
            No completed alerts yet. Use <strong>Draft Email</strong> on an alert above, then click <strong>Mark as done</strong> in the modal to see it here.
          </div>
        )}
      </div>

      <DraftEmailModal alertId={draftEmailAlertId} onClose={() => setDraftEmailAlertId(null)} onMarkDone={() => { setDraftEmailAlertId(null); fetchPulse(); fetchCompleted(); }} />
    </>
  );
}