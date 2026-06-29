import React, { createContext, useContext, useMemo, useState } from "react";

type LayoutContextValue = {
  pageTitle: string;
  setPageTitle: (t: string) => void;
  headerExtra: React.ReactNode;
  setHeaderExtra: (node: React.ReactNode) => void;
};

const LayoutContext = createContext<LayoutContextValue | null>(null);

export function LayoutProvider({ children }: { children: React.ReactNode }) {
  const [pageTitle, setPageTitle] = useState("Dashboard");
  const [headerExtra, setHeaderExtra] = useState<React.ReactNode>(null);
  const value = useMemo(
    () => ({ pageTitle, setPageTitle, headerExtra, setHeaderExtra }),
    [pageTitle, headerExtra]
  );
  return (
    <LayoutContext.Provider value={value}>{children}</LayoutContext.Provider>
  );
}

export function useLayout() {
  const ctx = useContext(LayoutContext);
  if (!ctx) throw new Error("useLayout must be used within LayoutProvider");
  return ctx;
}
