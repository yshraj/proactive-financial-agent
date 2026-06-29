/**
 * Demo constants and deep links for live presentations.
 * Uses dynamic client IDs from API data where possible — never hardcode UUIDs in UI.
 */
import { ROUTES, briefForClient, chatForClient } from "./routes";

/** Compelling book-wide question for live demos (ISA allowance story). */
export const DEMO_COPILOT_QUERY =
  "Show me everyone with ISA allowance still available this tax year";

/** Client-scoped demo question when scoped to a household. */
export const DEMO_CLIENT_QUERY = "Summarise open action items for this client";

/** Suggested live-demo order (for docs and optional UI hints). */
export const DEMO_WALKTHROUGH = [
  { route: ROUTES.dashboard, label: "Morning dashboard", seconds: 60 },
  { route: ROUTES.brief, label: "Meeting brief", seconds: 90 },
  { route: ROUTES.chat, label: "AI Copilot", seconds: 90 },
  { route: ROUTES.clients, label: "Client 360", seconds: 45 },
  { route: ROUTES.ingestion, label: "Document ingestion", seconds: 45 },
] as const;

/** Deep link to Copilot with optional auto-ask query. */
export function chatWithQuery(query: string, clientId?: string): string {
  const params = new URLSearchParams();
  if (clientId) params.set("clientId", clientId);
  params.set("q", query);
  return `${ROUTES.chat}?${params.toString()}`;
}

export { briefForClient, chatForClient };
