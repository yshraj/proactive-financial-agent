import { AlertTriangle, Check, Loader2, Sparkles } from "lucide-react";
import { Card } from "../ui";
import type { AgentStep } from "../../lib/agent";

type AgentTimelineProps = {
  steps: AgentStep[];
  title?: string;
  query?: string;
  compact?: boolean;
};

function StepIcon({ status }: { status: AgentStep["status"] }) {
  if (status === "DONE") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
        <Check className="h-3 w-3" aria-hidden />
      </span>
    );
  }
  if (status === "ERROR") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-amber-100 text-amber-700">
        <AlertTriangle className="h-3 w-3" aria-hidden />
      </span>
    );
  }
  return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ai-100 text-ai-700">
      <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
    </span>
  );
}

function stepSubtext(step: AgentStep): string | null {
  const detail = step.detail as Record<string, unknown> | null | undefined;
  if (!detail) return null;
  if (typeof detail.summary === "string" && detail.summary) return detail.summary;
  if (typeof detail.reason === "string" && detail.reason) return detail.reason;
  if (typeof detail.model === "string" && detail.model) return String(detail.model);
  return null;
}

/**
 * The real agent step timeline: plan, tool calls, synthesis, and compliance
 * review as they actually execute server-side (polled from agent_steps) —
 * replacing the old simulated thinking card on the copilot surface.
 */
export function AgentTimeline({
  steps,
  title = "AI Copilot is thinking",
  query,
  compact = false,
}: AgentTimelineProps) {
  const body = (
    <div className="min-w-0 flex-1">
      <p className="mb-1 text-sm font-semibold text-slate-950">{title}</p>
      {query && !compact && (
        <p className="mb-3 line-clamp-2 text-xs text-slate-500">&ldquo;{query}&rdquo;</p>
      )}
      {steps.length === 0 ? (
        <div className="space-y-2" aria-hidden>
          <p className="mb-2 text-xs text-ai-700">Contacting agents…</p>
          <div className="skeleton h-3 w-3/4" />
          <div className="skeleton h-3 w-1/2" />
        </div>
      ) : (
        <ol className="space-y-2" aria-label="Agent progress">
          {steps.map((step) => {
            const subtext = stepSubtext(step);
            return (
              <li key={step.seq} className="flex items-start gap-2.5">
                <StepIcon status={step.status} />
                <div className="min-w-0">
                  <p
                    className={
                      step.status === "RUNNING"
                        ? "text-xs font-medium text-ai-700"
                        : "text-xs font-medium text-slate-700"
                    }
                  >
                    {step.label}
                    {step.status === "RUNNING" ? "…" : ""}
                  </p>
                  {subtext && step.status !== "RUNNING" && (
                    <p className="truncate text-[11px] text-slate-400">{subtext}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );

  if (compact) {
    return (
      <div
        className="flex items-start gap-3 py-2"
        aria-busy="true"
        aria-label={title}
        data-testid="agent-timeline"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-ai-600 text-white">
          <Sparkles className="h-4 w-4 animate-pulse" aria-hidden />
        </span>
        {body}
      </div>
    );
  }

  return (
    <Card className="animate-fade-in" data-testid="agent-timeline">
      <div className="flex items-start gap-4 px-6 py-6" aria-busy="true" aria-label={title}>
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-ai-600 text-white shadow-xs">
          <Sparkles className="h-5 w-5 animate-pulse" aria-hidden />
        </span>
        {body}
      </div>
    </Card>
  );
}
