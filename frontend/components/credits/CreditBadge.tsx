import Link from "next/link";
import { Sparkles } from "lucide-react";
import { useCredits } from "@/contexts/CreditContext";
import { creditWarningLevel } from "@/lib/credits";

export function CreditBadge({ className = "" }: { className?: string }) {
  const { summary, isLoading } = useCredits();
  const remaining = summary?.remaining;
  const level = remaining == null ? null : creditWarningLevel(remaining);
  const tone =
    level === 0
      ? "border-red-200 bg-red-50 text-red-700"
      : level === 1 || level === 5
        ? "border-red-200 bg-red-50 text-red-700"
        : level === 10
          ? "border-orange-200 bg-orange-50 text-orange-800"
          : level === 20
            ? "border-amber-200 bg-amber-50 text-amber-800"
            : "border-brand-100 bg-brand-50 text-brand-700";

  return (
    <Link
      href="/settings#ai-credits"
      className={`inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 text-xs font-medium ${tone} ${className}`}
      aria-label={
        remaining == null
          ? "AI credit balance unavailable"
          : `${remaining} AI credits remaining`
      }
      data-testid="credit-badge"
    >
      <Sparkles className="h-3.5 w-3.5" aria-hidden />
      <span>{isLoading ? "Credits…" : remaining == null ? "Credits unavailable" : `${remaining} credits`}</span>
    </Link>
  );
}
