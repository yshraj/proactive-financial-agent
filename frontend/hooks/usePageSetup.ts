import { useEffect, type ReactNode } from "react";
import { useLayout } from "../contexts/LayoutContext";

/** Set page title and optional header extra; clears header on unmount. */
export function usePageSetup(
  title: string,
  headerExtra?: ReactNode | null,
  deps: unknown[] = []
) {
  const { setPageTitle, setHeaderExtra } = useLayout();

  useEffect(() => {
    setPageTitle(title);
  }, [setPageTitle, title]);

  useEffect(() => {
    setHeaderExtra(headerExtra ?? null);
    return () => setHeaderExtra(null);
    // headerExtra is a new React element each render; caller `deps` control when to refresh it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setHeaderExtra, ...deps]);
}
