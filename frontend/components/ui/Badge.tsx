import React from "react";

export function Badge({
  className = "",
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ring-black/[0.04] ${className}`}
    >
      {children}
    </span>
  );
}

export default Badge;
