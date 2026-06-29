import React, { memo, useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { ChevronDown, ChevronUp, RefreshCw, Sparkles } from "lucide-react";
import { AiBadge, AiThinkingCard, AiTrustFooter } from "./ai";
import { Card, Button, ErrorState } from "./ui";
import { useDigest } from "../hooks/useApi";
import { aiErrorMessage } from "../lib/ai";

const AiMarkdown = dynamic(
  () => import("./ai/AiMarkdown").then((m) => m.AiMarkdown),
  { ssr: false, loading: () => null }
);

type DigestCardProps = {
  simulatedDate: string;
};

const DIGEST_STEPS = [
  "Reviewing today's open priorities",
  "Checking overdue follow-ups",
  "Drafting your morning briefing",
];

function collapseKey(date: string) {
  return `kritifin-digest-collapsed:${date}`;
}

function DigestCard({ simulatedDate }: DigestCardProps) {
  const [refreshing, setRefreshing] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  const { data, isLoading, isError, error, isFetching, refreshDigest } = useDigest(
    simulatedDate,
    !collapsed
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(collapseKey(simulatedDate));
    if (stored === "1") setCollapsed(true);
  }, [simulatedDate]);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !(prev ?? false);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(collapseKey(simulatedDate), next ? "1" : "0");
      }
      return next;
    });
  }, [simulatedDate]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await refreshDigest();
    } finally {
      setRefreshing(false);
    }
  }, [refreshDigest]);

  return (
    <Card
      className="mb-8 overflow-hidden border-ai-100 bg-gradient-to-br from-ai-50/80 to-white"
      data-testid="dashboard-digest-card"
    >
      <div className="flex items-start justify-between gap-3 border-b border-ai-100/80 px-5 py-4 sm:px-6">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-ai-600 text-white">
            <Sparkles className="h-4 w-4" aria-hidden />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-950">Today&apos;s briefing</h2>
              <AiBadge label="Morning digest" />
            </div>
            <p className="mt-0.5 text-sm text-slate-500">
              AI summary of what deserves your attention on this date.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRefresh}
            loading={refreshing || (isFetching && !isLoading)}
            leftIcon={<RefreshCw className="h-4 w-4" aria-hidden />}
            aria-label="Regenerate briefing"
          >
            Refresh
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleCollapsed}
            leftIcon={
              collapsed ? (
                <ChevronDown className="h-4 w-4" aria-hidden />
              ) : (
                <ChevronUp className="h-4 w-4" aria-hidden />
              )
            }
            aria-expanded={!collapsed}
            aria-controls="digest-content"
          >
            {collapsed ? "Show" : "Hide"}
          </Button>
        </div>
      </div>

      {!collapsed && (
        <div id="digest-content" className="px-5 py-5 sm:px-6">
          {isLoading && (
            <AiThinkingCard
              title="Preparing your morning briefing"
              steps={DIGEST_STEPS}
              compact
            />
          )}
          {isError && (
            <ErrorState
              compact
              title="Couldn't generate briefing"
              message={aiErrorMessage(error, "digest")}
              onRetry={handleRefresh}
            />
          )}
          {data?.digest && !isLoading && (
            <div className="animate-fade-in" data-testid="digest-content-text">
              <AiMarkdown compact linkCitations={false}>
                {data.digest}
              </AiMarkdown>
              <AiTrustFooter
                generatedAt={data.generated_at}
                compact
                disclaimer="Prioritisation aid only — verify against your dashboard alerts before acting."
              />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export default memo(DigestCard);
