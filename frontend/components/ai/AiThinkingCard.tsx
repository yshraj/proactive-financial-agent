import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { Card } from "../ui";
import { isPageHidden } from "../../lib/polling";

const DEFAULT_STEPS = [
  "Searching structured client records",
  "Retrieving relevant document excerpts",
  "Cross-referencing alerts and deadlines",
  "Synthesising your answer",
];

type AiThinkingCardProps = {
  title?: string;
  steps?: string[];
  query?: string;
  compact?: boolean;
};

/** Staged loading card that conveys progress without streaming. */
export function AiThinkingCard({
  title = "AI Copilot is thinking",
  steps = DEFAULT_STEPS,
  query,
  compact = false,
}: AiThinkingCardProps) {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    setStepIndex(0);
    // Pure UI animation (no network) — still pause it while the tab is
    // backgrounded so a hidden thinking card doesn't keep re-rendering.
    let id: ReturnType<typeof setInterval> | null = null;
    const tick = () => setStepIndex((i) => (i + 1) % steps.length);
    const start = () => {
      if (id == null) id = setInterval(tick, 900);
    };
    const stop = () => {
      if (id != null) {
        clearInterval(id);
        id = null;
      }
    };
    const onVisibility = () => (isPageHidden() ? stop() : start());
    if (!isPageHidden()) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [steps, query]);

  if (compact) {
    return (
      <div className="flex items-center gap-3 py-2" aria-busy="true" aria-label={title}>
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-ai-600 text-white">
          <Sparkles className="h-4 w-4 animate-pulse" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-700">{steps[stepIndex]}…</p>
        </div>
      </div>
    );
  }

  return (
    <Card className="animate-fade-in">
      <div className="flex items-start gap-4 px-6 py-6">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-ai-600 text-white shadow-xs">
          <Sparkles className="h-5 w-5 animate-pulse" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="mb-1 text-sm font-semibold text-slate-950">{title}</p>
          {query && (
            <p className="mb-3 line-clamp-2 text-xs text-slate-500">
              &ldquo;{query}&rdquo;
            </p>
          )}
          <p className="mb-4 text-xs text-ai-700 transition-opacity duration-300">
            {steps[stepIndex]}…
          </p>
          <div className="space-y-2">
            <div className="skeleton h-3 w-3/4" />
            <div className="skeleton h-3 w-full" />
            <div className="skeleton h-3 w-5/6" />
          </div>
        </div>
      </div>
    </Card>
  );
}
