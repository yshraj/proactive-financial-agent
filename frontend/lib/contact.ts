// Shared types + validators for the conversational contact/support widget.
// Validation runs client-side for instant feedback and again server-side
// (backend/app/routers/contact.py) — never trust the browser alone.

export type ContactTopic = "sales" | "support" | "bug" | "general";

export interface ContactPayload {
  name: string;
  email: string;
  topic: ContactTopic;
  message: string;
  // Honeypot: real visitors never see or fill this field. Always sent empty.
  website: string;
}

export interface ContactResponse {
  ok: boolean;
}

export const CONTACT_TOPICS: { value: ContactTopic; label: string }[] = [
  { value: "sales", label: "Book a demo" },
  { value: "support", label: "Support" },
  { value: "bug", label: "Report an issue" },
  { value: "general", label: "Something else" },
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[a-zA-Z]{2,}$/;

/** Returns a friendly correction message, or null when the value is valid. */
export function validateName(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "Mind sharing your name?";
  if (trimmed.length > 120) return "That's a long name — keep it under 120 characters.";
  return null;
}

export function validateEmail(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "What's the best email to reach you at?";
  if (!EMAIL_RE.test(trimmed)) return "Hmm, that doesn't look like a valid email — mind double-checking?";
  return null;
}

export function validateMessage(value: string): string | null {
  const trimmed = value.trim();
  if (trimmed.length < 10) return "A few more details would help (at least 10 characters).";
  if (trimmed.length > 4000) return "That's a lot of detail — please keep it under 4000 characters.";
  return null;
}
