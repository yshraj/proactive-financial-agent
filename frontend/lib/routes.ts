// Central route table. Keeping navigation targets in one place makes it easy
// to evolve routing without hunting through components.
export const ROUTES = {
  home: "/",
  login: "/login",
  signup: "/signup",
  dashboard: "/dashboard",
  chat: "/chat",
  brief: "/brief",
  alerts: "/alerts",
  ingestion: "/admin",
  settings: "/settings",
} as const;

/** Where a visitor lands after authenticating (or when auth is not configured). */
export const APP_ENTRY: string = ROUTES.dashboard;

/**
 * Destination for the marketing "Get Started" / "Sign in" calls to action.
 * Points at the login page; the login page itself routes on into the app.
 */
export const GET_STARTED_HREF: string = ROUTES.login;

/** Routes that render without the authenticated app shell (sidebar/header). */
export const BARE_ROUTES: ReadonlySet<string> = new Set([
  ROUTES.home,
  ROUTES.login,
  ROUTES.signup,
]);
