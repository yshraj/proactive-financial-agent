import { useState } from "react";
import { ChevronLeft, ChevronRight, History } from "lucide-react";
import { Button, Card, CardHeader, ErrorState } from "@/components/ui";
import { useCreditHistory } from "@/hooks/useCreditsApi";
import { formatDateTime } from "@/lib/format";
import { creditCostLabel } from "@/lib/credits";

const PAGE_SIZE = 10;

export function CreditHistoryCard() {
  const [page, setPage] = useState(0);
  const query = useCreditHistory(PAGE_SIZE, page * PAGE_SIZE);
  const entries = query.data?.entries ?? [];
  const total = query.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Card id="credit-history" data-testid="credit-history">
      <CardHeader
        title="Credit history"
        description="Completed charges and balance changes."
      />
      <div className="px-5 py-4 sm:px-6">
        {query.isLoading ? (
          <p className="flex items-center gap-2 text-sm text-slate-500" role="status">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-brand-600" aria-hidden />
            Loading credit history…
          </p>
        ) : query.isError ? (
          <ErrorState message="Couldn't load credit history." onRetry={() => query.refetch()} />
        ) : entries.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-slate-500">
            <History className="h-4 w-4" aria-hidden /> No credit activity yet.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {entries.map((entry) => (
              <li key={entry.id} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-slate-800">
                      {creditCostLabel(entry.feature)}
                    </p>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium capitalize text-slate-600">
                      {entry.status.replaceAll("_", " ")}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-600">{entry.description}</p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {formatDateTime(entry.created_at)}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-sm font-semibold text-slate-800">
                    {entry.delta > 0 ? "+" : ""}{entry.delta}
                  </p>
                  <p className="text-xs text-slate-500">{entry.balance_after} remaining</p>
                </div>
              </li>
            ))}
          </ul>
        )}
        {total > PAGE_SIZE && (
          <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4">
            <p className="text-xs text-slate-500">Page {page + 1} of {pages}</p>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setPage((p) => p - 1)} disabled={page === 0} aria-label="Previous credit history page">
                <ChevronLeft className="h-4 w-4" aria-hidden />
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setPage((p) => p + 1)} disabled={page + 1 >= pages} aria-label="Next credit history page">
                <ChevronRight className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
