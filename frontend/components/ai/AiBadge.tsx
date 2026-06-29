import { Sparkles } from "lucide-react";

type AiBadgeProps = {
  label?: string;
  className?: string;
};

/** Small trust indicator for AI-generated content. */
export function AiBadge({ label = "AI-generated", className = "" }: AiBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full bg-ai-50 px-2 py-0.5 text-[11px] font-medium text-ai-700 ring-1 ring-ai-100 ${className}`}
    >
      <Sparkles className="h-3 w-3" aria-hidden />
      {label}
    </span>
  );
}
