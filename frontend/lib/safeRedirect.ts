import { APP_ENTRY } from "./routes";

/** Allowlist internal redirect paths; reject protocol-relative and external URLs. */
export function safeRedirectPath(raw: string | string[] | undefined): string {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (!value || typeof value !== "string") return APP_ENTRY;
  if (!value.startsWith("/")) return APP_ENTRY;
  if (value.startsWith("//")) return APP_ENTRY;
  if (value.includes("\\") || value.includes("@")) return APP_ENTRY;
  // Restrict to safe path characters
  if (!/^\/[a-zA-Z0-9_\-./?=&%]*$/.test(value)) return APP_ENTRY;
  return value;
}
