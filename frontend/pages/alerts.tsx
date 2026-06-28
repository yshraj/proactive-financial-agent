import Head from "next/head";
import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
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
  TableSkeleton,
} from "../components/ui";
import { useAlerts } from "../hooks/useApi";
import { formatDate, todayISO } from "../lib/format";
import {
  alertTypeBadge,
  alertTypeLabel,
  priorityBadge,
  priorityLabel,
} from "../lib/labels";

const TYPE_OPTIONS = ["All", "DEADLINE", "OPPORTUNITY", "COMPLIANCE", "REVIEW_OVERDUE", "FOLLOW_UP"];
const PRIORITY_OPTIONS = ["All", "HIGH", "MEDIUM", "LOW"];
const STATUS_OPTIONS = ["All", "PENDING", "COMPLETED"];
const DAYS_OPTIONS = [30, 90, 180, 365];

function Filter({
  label,
  value,
  onChange,
  options,
  format,
}: {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  options: (string | number)[];
  format?: (o: string | number) => string;
}) {
  return (
    <label className="flex items-center gap-2">
      <span className="text-xs font-medium text-gray-500">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {format ? format(o) : o}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function AlertsPage() {
  const { setPageTitle, setHeaderExtra } = useLayout();
  const [simulatedDate, setSimulatedDate] = useState(todayISO);
  const [days, setDays] = useState(90);
  const [typeFilter, setTypeFilter] = useState("All");
  const [priorityFilter, setPriorityFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const [draftEmailAlertId, setDraftEmailAlertId] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useAlerts({
    simulated_date: simulatedDate,
    days,
    type: typeFilter,
    priority: priorityFilter,
    status: statusFilter,
  });
  const alerts = data?.alerts ?? [];

  useEffect(() => {
    setPageTitle("Alerts");
    setHeaderExtra(
      <DateSimulator value={simulatedDate} onChange={setSimulatedDate} />
    );
    return () => setHeaderExtra(null);
  }, [setPageTitle, setHeaderExtra, simulatedDate]);

  return (
    <>
      <Head>
        <title>Alerts — Jarvis</title>
      </Head>

      <p className="mb-6 max-w-2xl text-sm leading-relaxed text-gray-500">
        View and filter all client alerts in one place. Use the date picker and
        filters to narrow the list, then draft a personalised email for any alert.
      </p>

      <div className="mb-6 flex flex-wrap items-center gap-4">
        <Filter label="Window" value={days} onChange={(v) => setDays(Number(v))} options={DAYS_OPTIONS} format={(o) => `Next ${o} days`} />
        <Filter label="Type" value={typeFilter} onChange={setTypeFilter} options={TYPE_OPTIONS} format={(o) => (o === "All" ? "All" : alertTypeLabel(String(o)))} />
        <Filter label="Priority" value={priorityFilter} onChange={setPriorityFilter} options={PRIORITY_OPTIONS} />
        <Filter label="Status" value={statusFilter} onChange={setStatusFilter} options={STATUS_OPTIONS} />
      </div>

      {isError ? (
        <ErrorState message={(error as Error)?.message} onRetry={() => refetch()} />
      ) : (
        <Card className="overflow-hidden">
          <CardHeader
            title="All alerts"
            description={
              isLoading
                ? "Loading…"
                : `${alerts.length} alert${alerts.length !== 1 ? "s" : ""} in the next ${days} days from ${formatDate(simulatedDate)}`
            }
          />
          {isLoading ? (
            <TableSkeleton rows={6} />
          ) : alerts.length === 0 ? (
            <EmptyState
              icon={<Bell className="h-5 w-5" aria-hidden />}
              title="No alerts match these filters"
              description="Try a different date, a wider window, or reset the filters above."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    {["Client", "Type", "Priority", "Due date", "Status", ""].map((h, i) => (
                      <th
                        key={h || i}
                        className={`px-6 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 ${i === 5 ? "text-right" : "text-left"}`}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((row) => {
                    const isCompleted = row.status === "COMPLETED";
                    return (
                      <tr
                        key={row.id}
                        className={`border-b border-gray-50 last:border-0 hover:bg-gray-50/50 ${isCompleted ? "bg-gray-50/50" : ""}`}
                      >
                        <td className={`px-6 py-4 font-medium ${isCompleted ? "text-gray-500" : "text-gray-900"}`}>
                          {row.client_name}
                        </td>
                        <td className="px-6 py-4">
                          <Badge className={`${alertTypeBadge(row.type)} ${isCompleted ? "opacity-70" : ""}`}>
                            {alertTypeLabel(row.type)}
                          </Badge>
                        </td>
                        <td className="px-6 py-4">
                          <Badge className={`${priorityBadge(row.priority)} ${isCompleted ? "opacity-70" : ""}`}>
                            {priorityLabel(row.priority)}
                          </Badge>
                        </td>
                        <td className={`px-6 py-4 ${isCompleted ? "text-gray-400" : "text-gray-600"}`}>
                          {formatDate(row.trigger_date)}
                        </td>
                        <td className="px-6 py-4">
                          <Badge className={isCompleted ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600"}>
                            {isCompleted ? "Done" : "Pending"}
                          </Badge>
                        </td>
                        <td className="px-6 py-4 text-right">
                          {isCompleted ? (
                            <span className="text-xs text-gray-400">Done</span>
                          ) : (
                            <Button size="sm" onClick={() => setDraftEmailAlertId(row.id)}>
                              Draft email
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <DraftEmailModal
        alertId={draftEmailAlertId}
        onClose={() => setDraftEmailAlertId(null)}
        onMarkDone={() => {
          setDraftEmailAlertId(null);
          refetch();
        }}
      />
    </>
  );
}
