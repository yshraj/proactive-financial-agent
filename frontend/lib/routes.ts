// Central route table. Keeping navigation targets in one place makes it easy
// to evolve routing without hunting through components.
export const ROUTES = {
  home: "/",
  dashboard: "/dashboard",
  chat: "/chat",
  brief: "/brief",
  alerts: "/alerts",
  ingestion: "/admin",
  settings: "/settings",
} as const;

/**
 * Destination for the marketing "Get Started" / "Sign in" calls to action.
 *
 * Authentication is not implemented yet, so this points straight into the app.
 * When auth lands, change this single constant to "/signup" or "/login" (or a
 * helper that redirects to the dashboard once authenticated) — no other
 * landing-page changes required.
 */
export const GET_STARTED_HREF: string = ROUTES.dashboard;

/** Routes that render without the authenticated app shell (sidebar/header). */
export const BARE_ROUTES: ReadonlySet<string> = new Set([ROUTES.home]);
