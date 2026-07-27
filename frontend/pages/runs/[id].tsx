import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, ShieldCheck, TriangleAlert } from "lucide-react";
import { AgentTimeline, AiBadge, AiMarkdown, AiSourceList } from "../../components/ai";
import { Card, EmptyState, ErrorState, PageIntro, PageShell } from "../../components/ui";
import { usePageSetup } from "../../hooks/usePageSetup";
import { fetchAgentRun, type AgentRun } from "../../lib/agent";

const STATUS_STYLES: Record<string, string> = {
  DONE: "bg-emerald-50 text-emerald-700",
  RUNNING: "bg-ai-50 text-ai-700",
  PENDING: "bg-slate-100 text-slate-600",
  ERROR: "bg-red-50 text-red-700",
};

function formatWhen(iso?: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("en-GB", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

/**
 * Agent run replay: the full recorded timeline (plan, tool calls, synthesis,
 * compliance review) plus the reviewed output — the audit view behind every
 * "View reasoning" link on copilot answers.
 */
export default function AgentRunDetailPage() {
  const router = useRouter();
  const runId = typeof router.query.id === "string" ? router.query.id : "";
  usePageSetup("Agent Run");

  const runQuery = useQuery<AgentRun>({
    queryKey: ["agent-run", runId],
    queryFn: () => fetchAgentRun(runId),
    enabled: !!runId,
    // Keep polling while the run is live so the replay doubles as a monitor.
    // 3s is plenty for a page that's secondary to the main chat/brief
    // surfaces (which poll faster via lib/agent.ts while the user is
    // actively waiting on an answer).
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "PENDING" || status === "RUNNING" ? 3000 : false;
    },
    // Explicit here (it's TanStack Query's default): don't keep polling once
    // the tab is backgrounded — resumes automatically on refocus.
    refetchIntervalInBackground: false,
  });

  const run = runQuery.data;
  const modelLabels = run?.output?.model_labels ?? {};

  return (
    <>
      <Head>
        <title>Agent Run - KritiFin</title>
      </Head>
      <PageShell>
        <PageIntro>
          Every copilot answer is produced by a recorded multi-agent run — plan, tool calls,
          synthesis, and a cross-model compliance review. This is the replay.
        </PageIntro>

        <div className="space-y-6" data-testid="agent-run-page">
          <Link
            href="/chat"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden /> Back to Copilot
          </Link>

          {runQuery.isLoading && (
            <Card className="p-6">
              <div className="space-y-2">
                <div className="skeleton h-4 w-1/3" />
                <div className="skeleton h-3 w-2/3" />
                <div className="skeleton h-3 w-1/2" />
              </div>
            </Card>
          )}

          {runQuery.isError && (
            <ErrorState
              title="Couldn't load this run"
              message="The run may have been cleared, or it belongs to a different workspace."
              onRetry={() => runQuery.refetch()}
            />
          )}

          {run && (
            <>
              <Card className="p-6">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-ai-600 text-white shadow-xs">
                    <Bot className="h-5 w-5" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <h2 className="text-base font-semibold text-slate-950">
                      {run.kind === "brief" ? "Pre-meeting brief run" : "Copilot run"}
                    </h2>
                    <p className="text-xs text-slate-500">
                      Started {formatWhen(run.created_at)}
                      {run.finished_at ? ` · finished ${formatWhen(run.finished_at)}` : ""}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${STATUS_STYLES[run.status] ?? STATUS_STYLES.PENDING}`}
                    data-testid="agent-run-status"
                  >
                    {run.status}
                  </span>
                </div>
                {Object.keys(modelLabels).length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {Object.entries(modelLabels).map(([stage, label]) => (
                      <span
                        key={stage}
                        className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] text-slate-600"
                      >
                        {stage}: <span className="font-medium">{label}</span>
                      </span>
                    ))}
                  </div>
                )}
                {run.error && (
                  <p className="mt-4 flex items-start gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-700">
                    <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {run.error}
                  </p>
                )}
              </Card>

              <Card className="p-6">
                <h3 className="mb-4 text-sm font-semibold text-slate-950">Execution timeline</h3>
                {run.steps.length === 0 ? (
                  <EmptyState
                    icon={<Bot className="h-5 w-5" aria-hidden />}
                    title="No steps recorded yet"
                    description="The run is queued — steps appear as the agents start working."
                  />
                ) : (
                  <AgentTimeline steps={run.steps} title="Recorded steps" compact />
                )}
              </Card>

              {run.output?.review && (
                <Card className="p-6">
                  <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-950">
                    <ShieldCheck className="h-4 w-4 text-emerald-600" aria-hidden />
                    Compliance review
                  </h3>
                  <p className="text-sm text-slate-600">
                    Verdict:{" "}
                    <span className="font-medium">
                      {run.output.review.verdict === "pass"
                        ? "Passed"
                        : run.output.review.verdict === "fail"
                          ? "Issues found"
                          : "Skipped (deterministic checks only)"}
                    </span>
                    {run.output.review.notes ? ` — ${run.output.review.notes}` : ""}
                  </p>
                  {run.output.review.issues.length > 0 && (
                    <ul className="mt-2 list-disc pl-5 text-sm text-slate-600">
                      {run.output.review.issues.map((issue) => (
                        <li key={issue}>{issue}</li>
                      ))}
                    </ul>
                  )}
                </Card>
              )}

              {run.status === "DONE" && run.output && (
                <Card className="p-6" data-testid="agent-run-output">
                  <div className="mb-3 flex items-center gap-2">
                    <AiBadge label={run.kind === "brief" ? "Brief" : "Answer"} />
                  </div>
                  <AiMarkdown compact linkCitations>
                    {run.output.answer}
                  </AiMarkdown>
                  {run.output.talking_points.length > 0 && (
                    <div className="mt-4">
                      <p className="ui-label mb-2">Talking points</p>
                      <ul className="list-disc pl-5 text-sm text-slate-700">
                        {run.output.talking_points.map((point) => (
                          <li key={point}>{point}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <AiSourceList sources={run.output.sources} />
                </Card>
              )}

              {(run.status === "PENDING" || run.status === "RUNNING") && (
                <AgentTimeline steps={run.steps} title="Agents working" />
              )}
            </>
          )}
        </div>
      </PageShell>
    </>
  );
}
