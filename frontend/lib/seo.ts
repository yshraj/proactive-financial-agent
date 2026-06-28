// Canonical site origin used for SEO tags, robots, and the sitemap.
// Set NEXT_PUBLIC_SITE_URL in production (e.g. https://app.jarvis.com).
export const SITE_URL: string = (
  process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"
).replace(/\/$/, "");

export const SITE_NAME = "Jarvis";

export const SITE_TITLE = "Jarvis — Proactive AI for financial advisers";

export const SITE_DESCRIPTION =
  "Jarvis turns client documents into priorities, pre-meeting briefs, and ready-to-send emails — so nothing slips and every meeting is prepared.";
