import React from "react";

type PageShellProps = {
  children: React.ReactNode;
  /** Default max width for most app pages; use wide for dashboard-style layouts. */
  wide?: boolean;
  className?: string;
};

/** Consistent horizontal rhythm and max-width for in-app pages. */
export function PageShell({ children, wide = false, className = "" }: PageShellProps) {
  return (
    <div
      className={`mx-auto w-full ${wide ? "max-w-[88rem]" : "max-w-6xl"} ${className}`}
    >
      {children}
    </div>
  );
}

export default PageShell;
