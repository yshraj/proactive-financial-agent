/**
 * Demo constants and deep links for live presentations.
 * Uses dynamic client IDs from API data where possible — never hardcode UUIDs in UI.
 */
import { ROUTES, briefForClient, chatForClient } from "./routes";

/** Compelling book-wide question for live demos (ISA allowance story). */
export const DEMO_COPILOT_QUERY =
  "Show me everyone with ISA allowance still available this tax year";

/** Deep link to Copilot with optional auto-ask query. */
export function chatWithQuery(query: string, clientId?: string): string {
  const params = new URLSearchParams();
  if (clientId) params.set("clientId", clientId);
  params.set("q", query);
  return `${ROUTES.chat}?${params.toString()}`;
}

export { briefForClient, chatForClient };
