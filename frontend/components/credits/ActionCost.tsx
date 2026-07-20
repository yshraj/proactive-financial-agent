import type { CreditFeature } from "@/lib/credits";
import { CREDIT_FEATURE_LABELS, getFeatureCost } from "@/lib/credits";
import { useCredits } from "@/contexts/CreditContext";

export function ActionCost({
  feature,
  className = "",
}: {
  feature: CreditFeature;
  className?: string;
}) {
  const { summary } = useCredits();
  const cost = getFeatureCost(summary?.costs, feature);
  if (cost == null || !summary) return null;
  const after = Math.max(0, summary.remaining - cost);
  return (
    <span
      className={`text-xs text-slate-500 ${className}`}
      data-testid={`credit-cost-${feature}`}
      aria-live="polite"
    >
      {CREDIT_FEATURE_LABELS[feature]} uses {cost} credit{cost === 1 ? "" : "s"} ·{" "}
      {after} remaining after completion
    </span>
  );
}
