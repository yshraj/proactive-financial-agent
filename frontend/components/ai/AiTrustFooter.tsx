import { Info } from "lucide-react";
import { AiBadge } from "./AiBadge";
import { formatGeneratedAt } from "@/lib/ai";

type AiTrustFooterProps = {
  generatedAt?: string;
  sourceCount?: number;
  disclaimer?: string;
  compact?: boolean;
};

export function AiTrustFooter({
  generatedAt,
  sourceCount,
  disclaimer = "For adviser use only — not regulated personal advice. Verify against source documents and your firm's compliance process.",
  compact = false,
}: AiTrustFooterProps) {
  const meta: string[] = [];
  if (generatedAt) meta.push(`Generated ${formatGeneratedAt(generatedAt)}`);
  if (sourceCount != null && sourceCount > 0) {
    meta.push(`${sourceCount} document source${sourceCount !== 1 ? "s" : ""}`);
  }

  if (compact) {
    return (
      <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-slate-500">
        <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
        <span>{disclaimer}</span>
      </p>
    );
  }

  return (
    <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <AiBadge />
        {meta.map((m) => (
          <span key={m} className="text-[11px] text-slate-500">
            {m}
          </span>
        ))}
      </div>
      <p className="max-w-md text-[11px] leading-relaxed text-slate-500">{disclaimer}</p>
    </div>
  );
}
