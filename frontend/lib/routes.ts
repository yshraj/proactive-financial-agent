// Central route table. Keeping navigation targets in one place makes it easy
// to evolve routing without hunting through components.
export const ROUTES = {
  home: "/",
  login: "/login",
  signup: "/signup",
  forgotPassword: "/forgot-password",
  resetPassword: "/reset-password",
  dashboard: "/dashboard",
  chat: "/chat",
  brief: "/brief",
  alerts: "/alerts",
  clients: "/clients",
  ingestion: "/admin",
  settings: "/settings",
} as const;

/** Deep link to Meeting Brief with a client pre-selected (and optional auto-generate). */
export function briefForClient(clientId: string, auto = true): string {
  const params = new URLSearchParams({ clientId });
  if (auto) params.set("auto", "1");
  return `${ROUTES.brief}?${params.toString()}`;
}

/** Deep link to AI Copilot scoped to one client. */
export function chatForClient(clientId: string): string {
  return `${ROUTES.chat}?clientId=${encodeURIComponent(clientId)}`;
}

/** Client 360° detail page. */
export function clientDetail(clientId: string): string {
  return `${ROUTES.clients}/${encodeURIComponent(clientId)}`;
}

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
  ROUTES.forgotPassword,
  ROUTES.resetPassword,
]);
