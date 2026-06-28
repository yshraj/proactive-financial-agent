import React from "react";

/**
 * Standard one-line description shown under a page title. Centralises the
 * intro paragraph styling that was previously duplicated across every page.
 */
export function PageIntro({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p className={`mb-8 max-w-2xl text-sm leading-relaxed text-gray-500 ${className}`}>
      {children}
    </p>
  );
}

export default PageIntro;
