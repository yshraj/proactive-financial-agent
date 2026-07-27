// Shared helpers for the app's hand-rolled status-polling loops (agent runs,
// upload jobs). Centralizes the "pause while nobody is looking" behavior so
// every polling loop pays the same, low tax on backend load:
//
// - Backgrounded tab (`document.visibilityState === "hidden"`): the browser
//   already throttles timers here, but we go further and skip the network
//   round-trip entirely until the tab is visible again — there's no UI to
//   update anyway.
// - Deliberately mirrors TanStack Query's own focus/visibility gate
//   (`focusManager`, see `refetchIntervalInBackground`) so hand-rolled loops
//   behave the same way as our `useQuery({ refetchInterval })` call sites.

/** True when the current tab is backgrounded. Always false outside the
 * browser (SSR, Node test runners) so loops behave the same as before there. */
export function isPageHidden(): boolean {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

/** Resolves immediately if the page is visible (or there's no `document`),
 * otherwise waits for the tab to come back into view. */
export function waitUntilVisible(): Promise<void> {
  if (!isPageHidden()) return Promise.resolve();
  return new Promise((resolve) => {
    const onChange = () => {
      if (!isPageHidden()) {
        document.removeEventListener("visibilitychange", onChange);
        resolve();
      }
    };
    document.addEventListener("visibilitychange", onChange);
  });
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Wait `ms`, then — if the tab is backgrounded — keep waiting until it's
 * visible again before letting the caller fire its next request.
 *
 * Use this in place of a bare `setTimeout`/`sleep` inside status-polling
 * loops (agent runs, upload jobs) so switching tabs away from a long-running
 * operation pauses the polling instead of hammering the status endpoint in
 * the background. The operation itself keeps running server-side either way.
 */
export async function pollDelay(ms: number): Promise<void> {
  await sleep(ms);
  await waitUntilVisible();
}
