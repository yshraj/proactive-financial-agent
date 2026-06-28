// Canonical site origin used for SEO tags, robots, and the sitemap.
// Set NEXT_PUBLIC_SITE_URL in production (e.g. https://kritifin.com).
export const SITE_URL: string = (
  process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"
).replace(/\/$/, "");

export const SITE_NAME = "KritiFin";

export const SITE_TITLE = "KritiFin - The AI operating system for financial advisers";

export const SITE_DESCRIPTION =
  "KritiFin brings together client intelligence, meeting preparation, compliance, and AI into one proactive workspace for financial advisers.";
