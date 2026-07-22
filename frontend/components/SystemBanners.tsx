import { useEffect, useState } from "react";
import { onSlowStart } from "../lib/api";

/**
 * App-wide connectivity and cold-start notices, rendered once in _app.
 *
 * - Offline: shown while the browser reports no connectivity. Data refetches
 *   automatically when the connection returns (TanStack Query
 *   refetchOnReconnect), so the banner only needs to inform, not act.
 * - Starting: shown when the very first backend response of the session is
 *   slow (serverless cold start), so the app never appears frozen.
 *
 * Both are polite live regions: announced by screen readers without
 * interrupting, and removed from the tree as soon as they stop being true.
 */
export function SystemBanners() {
  const [offline, setOffline] = useState(false);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    setOffline(typeof navigator !== "undefined" && navigator.onLine === false);
    const handleOnline = () => setOffline(false);
    const handleOffline = () => setOffline(true);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    const unsubscribe = onSlowStart((state) => setStarting(state === "slow"));
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      unsubscribe();
    };
  }, []);

  if (!offline && !starting) return null;

  return (
    <div className="fixed inset-x-0 top-0 z-[100] flex flex-col items-center gap-1 px-3 pt-2 pointer-events-none">
      {offline && (
        <div
          role="alert"
          aria-live="assertive"
          data-testid="offline-banner"
          className="pointer-events-auto flex items-center gap-2 rounded-full border border-amber-300 bg-amber-50 px-4 py-1.5 text-sm font-medium text-amber-900 shadow-sm"
        >
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-amber-500" />
          You&apos;re offline. Please check your internet connection. We&apos;ll
          reconnect automatically.
        </div>
      )}
      {!offline && starting && (
        <div
          role="status"
          aria-live="polite"
          data-testid="cold-start-banner"
          className="pointer-events-auto flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-sm text-slate-600 shadow-sm"
        >
          <span
            aria-hidden="true"
            className="h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600"
          />
          Starting the service… this may take a few seconds.
        </div>
      )}
    </div>
  );
}
