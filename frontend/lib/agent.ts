import { api, ApiError } from "./api";
import type { ChatSource } from "./types";

/** One recorded node/tool execution inside an agent run (the real timeline). */
export type AgentStep = {
  seq: number;
  node: string;
  label: string;
  status: "RUNNING" | "DONE" | "ERROR";
  detail?: Record<string, unknown> | null;
  started_at?: string | null;
  finished_at?: string | null;
};

export type AgentReview = {
  verdict: "pass" | "fail" | "skipped" | string;
  issues: string[];
  notes?: string;
};

export type AgentRunOutput = {
  answer: string;
  talking_points: string[];
  sources: ChatSource[];
  review?: AgentReview;
  model_labels?: Record<string, string>;
  plan_reason?: string;
};

export type AgentRun = {
  id: string;
  kind: "copilot" | "brief";
  status: "PENDING" | "RUNNING" | "DONE" | "ERROR";
  error?: string | null;
  output?: AgentRunOutput | null;
  steps: AgentStep[];
  conversation_id?: string | null;
  client_id?: string | null;
  created_at?: string | null;
  finished_at?: string | null;
};

type CreateRunResponse = {
  run_id: string;
  status: string;
  conversation_id?: string | null;
};

// Poll quickly while the run is fresh (steps stream into the timeline), then
// back off — mirrors the ingest job polling pattern.
const POLL_FAST_MS = 900;
const POLL_SLOW_MS = 2500;
const POLL_SLOW_AFTER_MS = 20_000;
// Worst case: a lost worker trigger recovered by the 5-minute scheduled drain.
const RUN_TIMEOUT_MS = 6 * 60 * 1000;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function fetchAgentRun(runId: string): Promise<AgentRun> {
  return api.get<AgentRun>(`/api/agent/runs/${encodeURIComponent(runId)}`);
}

export type CopilotRunResult = {
  runId: string;
  conversationId?: string;
  answer: string;
  sources: ChatSource[];
  review?: AgentReview;
};

/**
 * Ask the agent copilot: create a durable run, poll its real step timeline
 * (reported via `onSteps`), and resolve with the reviewed answer.
 *
 * Throws ApiError with the backend's public copy when the run fails, and an
 * `ai_unavailable`-coded ApiError when polling times out.
 */
export async function runCopilotWithProgress(params: {
  query: string;
  clientId?: string;
  conversationId?: string;
  onSteps?: (steps: AgentStep[]) => void;
}): Promise<CopilotRunResult> {
  const created = await api.post<CreateRunResponse>("/api/agent/runs", {
    kind: "copilot",
    query: params.query,
    ...(params.clientId ? { client_id: params.clientId } : {}),
    ...(params.conversationId ? { conversation_id: params.conversationId } : {}),
  });

  const started = Date.now();
  const deadline = started + RUN_TIMEOUT_MS;
  for (;;) {
    await sleep(Date.now() - started > POLL_SLOW_AFTER_MS ? POLL_SLOW_MS : POLL_FAST_MS);
    let run: AgentRun;
    try {
      run = await fetchAgentRun(created.run_id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        throw new ApiError("The agent run disappeared — please ask again.", 404);
      }
      throw e;
    }
    params.onSteps?.(run.steps ?? []);
    if (run.status === "DONE") {
      const output = run.output ?? ({} as AgentRunOutput);
      return {
        runId: run.id,
        conversationId: created.conversation_id ?? run.conversation_id ?? undefined,
        answer: output.answer ?? "",
        sources: output.sources ?? [],
        review: output.review,
      };
    }
    if (run.status === "ERROR") {
      throw new ApiError(
        run.error || "We couldn't generate AI results right now. Please try again in a few minutes.",
        503,
        undefined,
        { code: "ai_unavailable", retryable: true }
      );
    }
    if (Date.now() > deadline) {
      throw new ApiError(
        "The agents are taking longer than expected. Please try again shortly.",
        504,
        undefined,
        { code: "ai_unavailable", retryable: true }
      );
    }
  }
}

/** True when the error means the backend has no agent endpoints (older
 * deployment) and the caller should fall back to the synchronous chat API. */
export function isAgentUnsupported(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.status === 404 || error.status === 405) &&
    !/agent run disappeared/i.test(error.message)
  );
}
