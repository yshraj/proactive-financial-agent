import React from "react";
import Link, { LinkProps } from "next/link";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand-600 text-white shadow-xs hover:-translate-y-0.5 hover:bg-brand-500 hover:shadow-card-hover active:translate-y-0 active:bg-brand-700 disabled:translate-y-0 disabled:bg-brand-300 disabled:shadow-none",
  secondary:
    "border border-slate-200 bg-white text-slate-700 shadow-xs hover:-translate-y-0.5 hover:border-slate-300 hover:bg-slate-50 hover:shadow-card active:translate-y-0 active:bg-slate-100 disabled:translate-y-0 disabled:text-slate-400 disabled:shadow-none",
  ghost:
    "text-slate-600 hover:bg-slate-100 hover:text-slate-950 active:bg-slate-200 disabled:text-slate-400",
  danger:
    "border border-red-200 bg-white text-red-600 shadow-xs hover:-translate-y-0.5 hover:border-red-300 hover:bg-red-50 active:translate-y-0 active:bg-red-100 disabled:translate-y-0 disabled:opacity-50",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-4 text-sm",
  lg: "h-11 px-5 text-sm",
};

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all duration-200 disabled:cursor-not-allowed";

/** Single source of truth for button styling, shared by Button and ButtonLink. */
export function buttonClassName(
  variant: Variant = "primary",
  size: Size = "md",
  className = ""
): string {
  return `${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${className}`;
}

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: React.ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  leftIcon,
  className = "",
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={buttonClassName(variant, size, className)}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : (
        leftIcon
      )}
      {children}
    </button>
  );
}

export interface ButtonLinkProps
  extends LinkProps,
    Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, keyof LinkProps> {
  variant?: Variant;
  size?: Size;
  leftIcon?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}

/**
 * A Next.js Link styled as a button. Use for navigations that should look like
 * a button, instead of nesting <Button> inside <Link> (invalid <a><button>).
 */
export function ButtonLink({
  variant = "primary",
  size = "md",
  leftIcon,
  className = "",
  children,
  ...props
}: ButtonLinkProps) {
  return (
    <Link className={buttonClassName(variant, size, className)} {...props}>
      {leftIcon}
      {children}
    </Link>
  );
}

export default Button;
