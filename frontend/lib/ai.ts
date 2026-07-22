import { ApiError, OFFLINE_MESSAGE } from "./api";
import type { ChatSource } from "./types";

/** Turn inline [1] citations into markdown anchor links for source scroll. */
export function linkifyCitations(text: string): string {
  return text.replace(/\[(\d+)\]/g, "[$1](#source-$1)");
}

/** Map relevance score (0–1) to a human-readable confidence label. */
export function relevanceLabel(score?: number): "High" | "Medium" | "Low" | null {
  if (score == null) return null;
  if (score >= 0.55) return "High";
  if (score >= 0.38) return "Medium";
  return "Low";
}

export function relevanceBadgeClass(label: "High" | "Medium" | "Low"): string {
  if (label === "High") return "bg-emerald-100 text-emerald-800";
  if (label === "Medium") return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-600";
}

/** User-facing AI error messages with recovery hints. */
export function aiErrorMessage(error: unknown, context: "chat" | "brief" | "digest" | "draft" | "summary"): string {
  const base =
    error instanceof Error ? error.message : "Something went wrong generating the response.";
  const apiError = error instanceof ApiError ? error : null;

  // Offline beats everything: the honest state, already actionable.
  if (apiError?.code === "offline") return OFFLINE_MESSAGE;

  // Backend envelope codes are authoritative when present.
  if (apiError?.code === "ai_unavailable") {
    return "The AI assistant is temporarily unavailable. Please try again in a few minutes.";
  }
  if (apiError?.status === 503 && /search is temporarily unavailable/i.test(base)) {
    return "Search is temporarily unavailable. Please try again shortly.";
  }
  if (apiError?.status === 429 || apiError?.code === "rate_limited" || /429|rate limit/i.test(base)) {
    const wait = apiError?.retryAfterSeconds;
    return wait && wait > 0
      ? `Too many requests. Please wait a moment and try again. You can retry in about ${wait} seconds.`
      : "Too many requests. Please wait a moment and try again.";
  }
  if (/timed out|timeout/i.test(base)) {
    return "The request took too long. Your book may be large — try scoping to a single client or asking a narrower question.";
  }
  if (/404|not found/i.test(base)) {
    return context === "chat"
      ? "Client not found. Check the client scope or pick another client."
      : "The requested data could not be found.";
  }
  if (/network|connection|backend/i.test(base)) {
    return "Couldn't reach the AI service. Check your connection and that the backend is running.";
  }
  if (context === "chat" && /couldn't find|no client data/i.test(base)) {
    return base;
  }
  return base;
}

/** Contextual follow-up prompts based on the last question. */
export function getFollowUpSuggestions(
  lastQuery: string,
  clientScoped: boolean
): string[] {
  if (clientScoped) {
    const q = lastQuery.toLowerCase();
    if (/protection|gap/i.test(q)) {
      return [
        "What estate planning gaps should we discuss?",
        "Summarise this client's investment holdings",
        "What follow-ups are still outstanding?",
      ];
    }
    if (/action|follow.?up|overdue/i.test(q)) {
      return [
        "Draft a follow-up email for the highest-priority item",
        "What did we agree in recent meeting notes?",
        "Are there any compliance deadlines coming up?",
      ];
    }
    return [
      "What should I prioritise for our next meeting?",
      "Summarise recent meeting notes for this client",
      "Are there any protection or estate planning gaps?",
    ];
  }

  const q = lastQuery.toLowerCase();
  if (/review|overdue|12 month/i.test(q)) {
    return [
      "Which overdue review should I tackle first?",
      "Show me clients with reviews due this week",
      "Who hasn't had contact in over 6 months?",
    ];
  }
  if (/isa|allowance|tax/i.test(q)) {
    return [
      "Which clients have the largest unused ISA allowance?",
      "Who has cash excess we should discuss investing?",
      "Summarise upcoming tax-year deadlines",
    ];
  }
  if (/follow.?up|overdue|waiting/i.test(q)) {
    return [
      "Which follow-up is most overdue?",
      "Show me all high-priority open items",
      "What documents am I still waiting for?",
    ];
  }
  return [
    "What should I focus on first today?",
    "Which clients have reviews due this month?",
    "Show me all high-priority open alerts",
  ];
}

export function scrollToSource(ref: number) {
  const el = document.getElementById(`source-${ref}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    el.classList.add("ring-2", "ring-brand-400");
    setTimeout(() => el.classList.remove("ring-2", "ring-brand-400"), 1500);
  }
}

export function formatGeneratedAt(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-GB", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export type ChatTurn = {
  id: string;
  query: string;
  answer: string;
  sources: ChatSource[];
};
