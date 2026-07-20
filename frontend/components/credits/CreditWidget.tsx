import { Button } from "@/components/ui";
import { useCredits } from "@/contexts/CreditContext";
import { creditWarningLevel } from "@/lib/credits";

export function CreditWidget({
  compact = false,
  onRequest,
}: {
  compact?: boolean;
  onRequest?: () => void;
}) {
  const { summary, isLoading, isError, refetch } = useCredits();
  if (isLoading) {
    return <div className="h-16 animate-pulse rounded-xl bg-slate-100" aria-label="Loading AI credits" />;
  }
  if (isError || !summary) {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
        Balance unavailable.{" "}
        <button className="font-medium underline" onClick={() => refetch()} type="button">
          Try again
        </button>
      </div>
    );
  }
  const percent =
    summary.total_granted > 0
      ? Math.max(0, Math.min(100, (summary.remaining / summary.total_granted) * 100))
      : 0;
  const warning = creditWarningLevel(summary.remaining);
  const bar =
    warning === 0 || warning === 1 || warning === 5
      ? "bg-red-500"
      : warning === 10
        ? "bg-orange-500"
        : warning === 20
          ? "bg-amber-500"
          : "bg-brand-600";
  const warningText =
    warning === 0
      ? "You’re out of AI credits. Existing work remains available."
      : warning === 1
        ? "1 credit remains. Higher-cost actions need more credits."
        : warning === 5
          ? `${summary.remaining} credits remain. Check the cost before continuing.`
          : warning === 10
            ? `${summary.remaining} credits remain. You can request more at any time.`
            : warning === 20
              ? `${summary.remaining} credits remain. AI actions use different amounts.`
              : warning === 50
                ? `${summary.remaining} credits remain. Review costs before AI actions.`
                : "";
  const warningTone =
    warning === 0 || warning === 1 || warning === 5
      ? "text-red-700"
      : warning === 10
        ? "text-orange-700"
        : warning === 20
          ? "text-amber-700"
          : "text-brand-700";

  return (
    <div
      className={compact ? "rounded-xl border border-slate-200 bg-slate-50/70 p-3" : ""}
      data-testid={compact ? "credit-widget-compact" : "credit-widget"}
    >
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs font-medium text-slate-600">AI credits</p>
        <p className="text-xs text-slate-500">
          <strong className="font-semibold text-slate-900">{summary.remaining}</strong>
          {!compact && ` of ${summary.total_granted} remaining`}
        </p>
      </div>
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200"
        role="progressbar"
        aria-label="AI credits remaining"
        aria-valuemin={0}
        aria-valuemax={summary.total_granted}
        aria-valuenow={summary.remaining}
      >
        <div className={`h-full rounded-full ${bar}`} style={{ width: `${percent}%` }} />
      </div>
      {warning != null && (
        <p className={`mt-2 text-xs ${warningTone}`}>
          {warningText}
        </p>
      )}
      {!compact && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-slate-500">Credits do not renew automatically.</p>
          {onRequest && (summary.contact.request_enabled || summary.contact.email) && (
            <Button size="sm" variant="secondary" onClick={onRequest}>
              Request more credits
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export const CreditMeter = CreditWidget;
