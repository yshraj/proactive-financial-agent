import Head from "next/head";
import { useState, useEffect, useCallback } from "react";
import DateSimulator from "../components/DateSimulator";
import DraftEmailModal from "../components/DraftEmailModal";
import { useLayout } from "../contexts/LayoutContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatDate(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
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

const TYPE_OPTIONS = ["All", "DEADLINE", "OPPORTUNITY", "COMPLIANCE", "REVIEW_OVERDUE"];
const PRIORITY_OPTIONS = ["All", "HIGH", "MEDIUM", "LOW"];
const STATUS_OPTIONS = ["All", "PENDING", "COMPLETED"];
const DAYS_OPTIONS = [30, 90, 180, 365];

function typeBadgeClass(type: string): string {
  switch (type) {
    case "DEADLINE":
      return "bg-amber-100 text-amber-800";
    case "OPPORTUNITY":
      return "bg-emerald-100 text-emerald-800";
    case "REVIEW_OVERDUE":
      return "bg-violet-100 text-violet-800";
    case "COMPLIANCE":
      return "bg-indigo-100 text-indigo-800";
    default:
      return "bg-gray-100 text-gray-700";
  }
}

function priorityBadgeClass(priority: string): string {
  switch (priority) {
    case "HIGH":
      return "bg-red-100 text-red-700";
    case "MEDIUM":
      return "bg-sky-100 text-sky-700";
    case "LOW":
      return "bg-gray-100 text-gray-600";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

export default function AlertsPage() {
  const { setPageTitle, setHeaderExtra } = useLayout();
  const [simulatedDate, setSimulatedDate] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  });
  const [days, setDays] = useState(90);
  const [typeFilter, setTypeFilter] = useState("All");
  const [priorityFilter, setPriorityFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draftEmailAlertId, setDraftEmailAlertId] = useState<string | null>(null);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        simulated_date: simulatedDate,
        days: String(days),
      });
      if (typeFilter !== "All") params.set("type", typeFilter);
      if (priorityFilter !== "All") params.set("priority", priorityFilter);
      if (statusFilter !== "All") params.set("status", statusFilter);
      const res = await fetch(`${API_BASE}/api/monitor/alerts?${params}`);
      if (!res.ok) throw new Error(res.status === 404 ? "API not found" : `Failed: ${res.status}`);
      const data = await res.json();
      setAlerts(data.alerts ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load alerts");
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  }, [simulatedDate, days, typeFilter, priorityFilter, statusFilter]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  useEffect(() => {
    setPageTitle("Alerts");
    setHeaderExtra(
      <div className="flex items-center justify-end gap-4">
        <DateSimulator value={simulatedDate} onChange={setSimulatedDate} />
      </div>
    );
    return () => setHeaderExtra(null);
  }, [setPageTitle, setHeaderExtra, simulatedDate]);

  return (
    <>
      <Head>
        <title>Alerts – Jarvis</title>
      </Head>

      <p className="mb-6 text-sm leading-relaxed text-gray-500">
        View and filter all client alerts in one place. Use the date picker and filters to narrow the list. Draft Email opens a personalised draft for the selected alert.
      </p>

      {error && (
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
          {error}. Ensure the backend is running.
        </div>
      )}

      <div className="mb-6 flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500">Window</span>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
          >
            {DAYS_OPTIONS.map((d) => (
              <option key={d} value={d}>
                Next {d} days
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500">Type</span>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
          >
            {TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500">Priority</span>
          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
          >
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500">Status</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-card">
        <div className="border-b border-gray-100 px-6 py-5">
          <h2 className="text-base font-semibold text-gray-900">All alerts</h2>
          {!loading && (
            <p className="mt-1 text-sm text-gray-500">
              {alerts.length} alert{alerts.length !== 1 ? "s" : ""} in the next {days} days from {simulatedDate}
            </p>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Client</th>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Type</th>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Priority</th>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Due date</th>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
                <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && alerts.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                    No alerts match the selected filters. Try a different date, window, or filter.
                  </td>
                </tr>
              )}
              {!loading &&
                alerts.map((row) => {
                  const isCompleted = row.status === "COMPLETED";
                  return (
                    <tr
                      key={row.id}
                      className={`border-b border-gray-50 last:border-0 hover:bg-gray-50/50 ${isCompleted ? "bg-gray-50/50" : ""}`}
                    >
                      <td className={`px-6 py-4 font-medium ${isCompleted ? "text-gray-500" : "text-gray-900"}`}>{row.client_name}</td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${typeBadgeClass(row.type)} ${isCompleted ? "opacity-70" : ""}`}>
                          {row.type}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${priorityBadgeClass(row.priority)} ${isCompleted ? "opacity-70" : ""}`}>
                          {row.priority}
                        </span>
                      </td>
                      <td className={`px-6 py-4 ${isCompleted ? "text-gray-400" : "text-gray-600"}`}>{formatDate(row.trigger_date)}</td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${isCompleted ? "bg-emerald-100 text-emerald-700" : "text-gray-500"}`}>
                          {row.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        {isCompleted ? (
                          <span className="text-xs text-gray-400">Done</span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setDraftEmailAlertId(row.id)}
                            className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
                          >
                            Draft Email
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>

      <DraftEmailModal alertId={draftEmailAlertId} onClose={() => setDraftEmailAlertId(null)} onMarkDone={() => { setDraftEmailAlertId(null); fetchAlerts(); }} />
    </>
  );
}
