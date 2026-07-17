import Head from "next/head";
import { useState } from "react";
import { Bell } from "lucide-react";
import DateSimulator from "../components/DateSimulator";
import LazyDraftEmailModal from "../components/LazyDraftEmailModal";
import {
  Card,
  CardHeader,
  Button,
  ButtonLink,
  Badge,
  EmptyState,
  ErrorState,
  TableSkeleton,
  PageIntro,
  PageShell,
} from "../components/ui";
import { useDraftEmailModalState } from "../hooks/useDraftEmailModalState";
import { usePageSetup } from "../hooks/usePageSetup";
import { useAlerts } from "../hooks/useApi";
import { errorMessage } from "../lib/api";
import { formatDate, todayISO } from "../lib/format";
import { briefForClient } from "../lib/routes";
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
    <label className="flex flex-col gap-1.5">
      <span className="ui-label">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input w-auto min-w-[8rem] pr-8"
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
  const [simulatedDate, setSimulatedDate] = useState(todayISO);
  const [days, setDays] = useState(90);
  const [typeFilter, setTypeFilter] = useState("All");
  const [priorityFilter, setPriorityFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const { source: draftEmailSource, openAlertDraft, closeDraft } = useDraftEmailModalState();

  const { data, isLoading, isError, error, refetch } = useAlerts({
    simulated_date: simulatedDate,
    days,
    type: typeFilter,
    priority: priorityFilter,
    status: statusFilter,
  });
  const alerts = data?.alerts ?? [];

  usePageSetup(
    "Alerts",
    <DateSimulator value={simulatedDate} onChange={setSimulatedDate} />,
    [simulatedDate]
  );

  return (
    <>
      <Head>
        <title>Alerts - KritiFin</title>
      </Head>

      <PageShell wide>
      <PageIntro>
        Filter every client alert and draft a personalised email in a click.
      </PageIntro>

      <div className="mb-6 flex flex-wrap items-end gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs" data-testid="alerts-filters">
        <Filter label="Window" value={days} onChange={(v) => setDays(Number(v))} options={DAYS_OPTIONS} format={(o) => `Next ${o} days`} />
        <Filter label="Type" value={typeFilter} onChange={setTypeFilter} options={TYPE_OPTIONS} format={(o) => (o === "All" ? "All types" : alertTypeLabel(String(o)))} />
        <Filter label="Priority" value={priorityFilter} onChange={setPriorityFilter} options={PRIORITY_OPTIONS} format={(o) => (o === "All" ? "All priorities" : String(o))} />
        <Filter label="Status" value={statusFilter} onChange={setStatusFilter} options={STATUS_OPTIONS} format={(o) => (o === "All" ? "All statuses" : String(o))} />
      </div>

      {isError ? (
        <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
      ) : (
        <Card className="overflow-hidden" data-testid="alerts-table-card">
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
                  <tr className="border-b border-gray-200 bg-gray-50/60">
                    {["Client", "Type", "Priority", "Due date", "Status", ""].map((h, i) => (
                      <th
                        key={h || i}
                        className={`px-6 py-3 text-xs font-medium text-gray-500 ${i === 5 ? "text-right" : "text-left"}`}
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
                        className={`border-b border-gray-100 last:border-0 transition-colors hover:bg-gray-50/70 ${isCompleted ? "bg-gray-50/40" : ""}`}
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
                        <td className={`px-6 py-4 ${isCompleted ? "text-gray-500" : "text-gray-600"}`}>
                          {formatDate(row.trigger_date)}
                        </td>
                        <td className="px-6 py-4">
                          <Badge className={isCompleted ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-600"}>
                            {isCompleted ? "Done" : "Pending"}
                          </Badge>
                        </td>
                        <td className="px-6 py-4 text-right">
                          {isCompleted ? (
                            <span className="text-xs text-gray-500">Done</span>
                          ) : (
                            <div className="flex flex-wrap justify-end gap-2">
                              <ButtonLink
                                href={briefForClient(row.client_id)}
                                size="sm"
                                variant="secondary"
                                data-testid={`prep-brief-${row.id}`}
                              >
                                Prep brief
                              </ButtonLink>
                              <Button size="sm" onClick={() => openAlertDraft(row.id)}>
                                Draft email
                              </Button>
                            </div>
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

      {draftEmailSource && (
        <LazyDraftEmailModal source={draftEmailSource} onClose={closeDraft} onMarkDone={closeDraft} />
      )}
      </PageShell>
    </>
  );
}
