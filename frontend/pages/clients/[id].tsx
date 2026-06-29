import Head from "next/head";
import { useRouter } from "next/router";
import { useState } from "react";
import {
  ClipboardList,
  FileText,
  Gauge,
  ListChecks,
  MessageSquareText,
  Pencil,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import AlertCard from "../../components/AlertCard";
import EditClientModal from "../../components/EditClientModal";
import ReviewNoteModal from "../../components/ReviewNoteModal";
import LazyDraftEmailModal from "../../components/LazyDraftEmailModal";
import {
  Card,
  Button,
  ButtonLink,
  Badge,
  EmptyState,
  ErrorState,
  Skeleton,
  PageIntro,
  PageShell,
} from "../../components/ui";
import { useDraftEmailModalState } from "../../hooks/useDraftEmailModalState";
import { usePageSetup } from "../../hooks/usePageSetup";
import { useClientDetail, useClientReviewNote } from "../../hooks/useApi";
import { errorMessage } from "../../lib/api";
import { formatCurrency, formatDate, formatRiskScore } from "../../lib/format";
import { briefForClient, chatForClient, ROUTES } from "../../lib/routes";
import type { AlertType } from "../../lib/types";

export default function ClientDetailPage() {
  const router = useRouter();
  const clientId = typeof router.query.id === "string" ? router.query.id : undefined;
  const { source: draftEmailSource, openAlertDraft, closeDraft } = useDraftEmailModalState();
  const [isEditing, setIsEditing] = useState(false);
  const [showReviewNote, setShowReviewNote] = useState(false);
  const detailQuery = useClientDetail(clientId);
  const reviewNote = useClientReviewNote(clientId);
  const client = detailQuery.data;

  const openReviewNote = () => {
    setShowReviewNote(true);
    reviewNote.mutate();
  };

  usePageSetup(client?.full_name ?? "Client", null, [client?.full_name]);

  if (!clientId) {
    return null;
  }

  return (
    <>
      <Head>
        <title>{client?.full_name ?? "Client"} - KritiFin</title>
      </Head>

      <PageShell wide>
      {detailQuery.isLoading && (
        <div className="space-y-6" aria-busy="true">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      )}

      {detailQuery.isError && (
        <ErrorState
          title="Couldn't load client"
          message={errorMessage(detailQuery.error, "Couldn't load client.")}
          onRetry={() => detailQuery.refetch()}
        />
      )}

      {client && !detailQuery.isLoading && (
        <div className="space-y-6" data-testid="client-detail-page">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight text-slate-950">
                {client.full_name}
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Last review:{" "}
                {client.last_review_date ? formatDate(client.last_review_date) : "Not on file"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={() => setIsEditing(true)}
                leftIcon={<Pencil className="h-4 w-4" aria-hidden />}
                data-testid="client-edit-button"
              >
                Edit details
              </Button>
              <Button
                variant="secondary"
                onClick={openReviewNote}
                leftIcon={<ClipboardList className="h-4 w-4" aria-hidden />}
                data-testid="client-review-note-button"
              >
                Review note
              </Button>
              <ButtonLink
                href={briefForClient(client.id)}
                leftIcon={<FileText className="h-4 w-4" aria-hidden />}
                data-testid="client-prepare-button"
              >
                Prepare for meeting
              </ButtonLink>
              <ButtonLink
                href={chatForClient(client.id)}
                variant="secondary"
                leftIcon={<MessageSquareText className="h-4 w-4" aria-hidden />}
                data-testid="client-ask-button"
              >
                Ask about this client
              </ButtonLink>
            </div>
          </div>

          {client.summary && (
            <Card className="border-brand-100 bg-brand-50/40 p-6" data-testid="client-ai-summary">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Sparkles className="h-4 w-4 text-brand-600" aria-hidden />
                <h3 className="text-sm font-semibold text-brand-900">AI relationship summary</h3>
                <span className="inline-flex items-center gap-1 rounded-full bg-ai-50 px-2 py-0.5 text-[11px] font-medium text-ai-700 ring-1 ring-ai-100">
                  <Sparkles className="h-3 w-3" aria-hidden />
                  AI-generated
                </span>
              </div>
              <p className="text-sm leading-relaxed text-slate-700">{client.summary}</p>
              <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
                Based on profile data and open alerts. For document-grounded detail, use{" "}
                <ButtonLink href={chatForClient(client.id)} size="sm" variant="ghost" className="inline h-auto px-0 py-0 text-[11px]">
                  AI Copilot
                </ButtonLink>{" "}
                or generate a{" "}
                <ButtonLink href={briefForClient(client.id)} size="sm" variant="ghost" className="inline h-auto px-0 py-0 text-[11px]">
                  meeting brief
                </ButtonLink>
                .
              </p>
            </Card>
          )}

          <Card className="p-6">
            <h3 className="ui-label mb-4">Profile snapshot</h3>
            <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "Total assets", value: formatCurrency(client.total_assets) },
                { label: "Cash savings", value: formatCurrency(client.cash_savings) },
                {
                  label: "Risk score",
                  value: formatRiskScore(client.risk_score),
                },
                {
                  label: "Retirement target",
                  value: client.retirement_target_age != null ? `Age ${client.retirement_target_age}` : "—",
                },
                {
                  label: "Documents",
                  value: String(client.document_count ?? 0),
                },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
                  <dt className="text-xs font-medium text-slate-500">{label}</dt>
                  <dd className="mt-1 text-sm font-semibold text-slate-900">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>

          {(client.at_risk || (client.next_best_actions?.length ?? 0) > 0) && (
            <Card className="p-6" data-testid="client-intelligence">
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <Gauge className="h-4 w-4 text-brand-600" aria-hidden />
                <h3 className="text-sm font-semibold text-slate-900">Client intelligence</h3>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {client.at_risk && (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
                    <div className="flex items-center gap-2">
                      <ShieldAlert className="h-4 w-4 text-slate-500" aria-hidden />
                      <span className="text-xs font-medium text-slate-500">Engagement risk</span>
                      <Badge
                        className={
                          client.at_risk.level === "HIGH"
                            ? "bg-red-100 text-red-700"
                            : client.at_risk.level === "MEDIUM"
                              ? "bg-amber-100 text-amber-700"
                              : "bg-emerald-100 text-emerald-700"
                        }
                      >
                        {client.at_risk.level}
                      </Badge>
                    </div>
                    <p className="mt-2 text-sm font-semibold text-slate-900">
                      {client.at_risk.score}/100
                    </p>
                    <p className="mt-1 text-xs text-slate-500">{client.at_risk.rationale}</p>
                  </div>
                )}
                {client.planning_completeness && (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
                    <span className="text-xs font-medium text-slate-500">Profile completeness</span>
                    <p className="mt-2 text-sm font-semibold text-slate-900">
                      {client.planning_completeness.score}%
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {client.planning_completeness.missing.length > 0
                        ? `Missing: ${client.planning_completeness.missing.join(", ")}`
                        : "All key fields captured."}
                    </p>
                  </div>
                )}
              </div>

              {(client.next_best_actions?.length ?? 0) > 0 && (
                <div className="mt-5">
                  <div className="mb-3 flex items-center gap-2">
                    <ListChecks className="h-4 w-4 text-brand-600" aria-hidden />
                    <h4 className="text-sm font-semibold text-slate-900">Next best actions</h4>
                  </div>
                  <ul className="space-y-2" data-testid="next-best-actions">
                    {client.next_best_actions!.map((nba, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3"
                      >
                        <Badge
                          className={
                            nba.priority === "HIGH"
                              ? "bg-red-100 text-red-700"
                              : "bg-slate-100 text-slate-600"
                          }
                        >
                          {nba.priority}
                        </Badge>
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-slate-900">{nba.action}</p>
                          <p className="text-xs text-slate-500">{nba.reason}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          )}

          <div>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-base font-semibold text-gray-900">Open alerts</h3>
              <Badge className="bg-gray-100 text-gray-600">
                {client.pending_alerts.length} item{client.pending_alerts.length !== 1 ? "s" : ""}
              </Badge>
            </div>
            {client.pending_alerts.length > 0 ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {client.pending_alerts.map((alert) => (
                  <AlertCard
                    key={alert.id}
                    type={alert.type as AlertType}
                    priority={alert.priority as "HIGH" | "MEDIUM" | "LOW"}
                    title={alert.title || "Alert"}
                    description={alert.description || ""}
                    prepareHref={briefForClient(client.id)}
                    onDraftEmail={() => openAlertDraft(alert.id)}
                  />
                ))}
              </div>
            ) : (
              <EmptyState
                title="No open alerts"
                description="This client has no pending items in the next 90 days."
              />
            )}
          </div>

          {client.overdue_follow_ups.length > 0 && (
            <Card className="overflow-hidden">
              <div className="border-b border-gray-100 px-6 py-4">
                <h3 className="text-sm font-semibold text-gray-900">Overdue follow-ups</h3>
              </div>
              <ul className="divide-y divide-gray-100">
                {client.overdue_follow_ups.map((alert) => (
                  <li
                    key={alert.id}
                    className="flex flex-wrap items-center justify-between gap-3 px-6 py-4"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900">
                        {alert.title || "Follow-up"}
                      </p>
                      <p className="text-xs text-amber-700">
                        Was due {formatDate(alert.trigger_date)}
                      </p>
                    </div>
                    <ButtonLink
                      href={briefForClient(client.id)}
                      size="sm"
                      variant="secondary"
                    >
                      Prepare
                    </ButtonLink>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {client.pending_alerts.length === 0 && client.overdue_follow_ups.length === 0 && (
            <PageIntro className="mb-0">
              Upload more documents in{" "}
              <a href={ROUTES.ingestion} className="text-brand-600 hover:underline">
                Ingestion
              </a>{" "}
              to enrich this client record.
            </PageIntro>
          )}
        </div>
      )}

      {draftEmailSource && (
        <LazyDraftEmailModal source={draftEmailSource} onClose={closeDraft} onMarkDone={closeDraft} />
      )}
      {client && isEditing && (
        <EditClientModal client={client} onClose={() => setIsEditing(false)} />
      )}
      {showReviewNote && (
        <ReviewNoteModal
          data={reviewNote.data}
          loading={reviewNote.isPending}
          onClose={() => setShowReviewNote(false)}
        />
      )}
      </PageShell>
    </>
  );
}
