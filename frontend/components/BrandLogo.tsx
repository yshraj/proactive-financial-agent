import React from "react";

type LogoSize = "sm" | "md" | "lg";

const SIZE_CLASSES: Record<LogoSize, string> = {
  sm: "h-8 w-8",
  md: "h-10 w-10",
  lg: "h-12 w-12",
};

/**
 * KritiFin's K monogram: two precise paths meeting at a data node, suggesting
 * guidance, connected intelligence, and upward client outcomes.
 */
export function KritiMark({
  size = "md",
  className = "",
}: {
  size?: LogoSize;
  className?: string;
}) {
  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-slate-950 text-white shadow-card ${SIZE_CLASSES[size]} ${className}`}
      aria-hidden
    >
      <span className="absolute inset-0 bg-[radial-gradient(circle_at_75%_20%,rgba(37,99,235,0.55),transparent_34%),linear-gradient(135deg,#0F172A_0%,#1E293B_55%,#2563EB_100%)]" />
      <svg viewBox="0 0 40 40" className="relative h-7 w-7" fill="none">
        <path
          d="M13 9v22"
          stroke="currentColor"
          strokeWidth="3.6"
          strokeLinecap="round"
        />
        <path
          d="M28 10 15 20l13 10"
          stroke="currentColor"
          strokeWidth="3.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="27.5" cy="10.5" r="2.4" fill="#93C5FD" />
      </svg>
    </span>
  );
}

export function BrandLogo({
  size = "md",
  showWordmark = true,
  className = "",
  wordmarkClassName = "",
}: {
  size?: LogoSize;
  showWordmark?: boolean;
  className?: string;
  wordmarkClassName?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <KritiMark size={size} />
      {showWordmark && (
        <span
          className={`text-sm font-semibold tracking-[-0.03em] text-slate-950 ${wordmarkClassName}`}
        >
          KritiFin
        </span>
      )}
    </span>
  );
}

export default BrandLogo;
