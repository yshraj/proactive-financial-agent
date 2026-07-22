export interface CreditSummary {
  total_granted: number;
  used: number;
  remaining: number;
  version: number;
  costs: Record<string, number>;
  contact: {
    email: string;
    request_enabled: boolean;
  };
}

export interface CreditHistoryEntry {
  id: string;
  created_at: string;
  feature: string;
  delta: number;
  balance_after: number;
  status: string;
  description: string;
}

export interface CreditHistoryResponse {
  entries: CreditHistoryEntry[];
  total: number;
}

export interface CreditRequestResponse {
  status: "pending";
  message: string;
}

/** Structured envelope on credit error responses (backend app/main.py). */
export interface CreditErrorDetail {
  error: {
    code: "insufficient_credits" | "credit_balance_unavailable" | string;
    message: string;
    retryable: boolean;
  };
  detail?: string;
  required?: number;
  remaining?: number;
  feature?: string;
  contact_available?: boolean;
}

/** Read the error code from a credit error payload (tolerates the legacy
 * string form so a stale cached bundle can't crash against an old backend). */
export function creditErrorCode(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const raw = (payload as { error?: unknown }).error;
  if (typeof raw === "string") return raw;
  if (raw && typeof raw === "object" && typeof (raw as { code?: unknown }).code === "string") {
    return (raw as { code: string }).code;
  }
  return null;
}

export type CreditFeature =
  | "chat"
  | "meeting_brief"
  | "draft_email"
  | "digest"
  | "review_note"
  | "document_upload"
  | "transcript";

export const CREDIT_FEATURE_LABELS: Record<CreditFeature, string> = {
  chat: "AI Copilot question",
  meeting_brief: "Meeting brief",
  draft_email: "Draft email",
  digest: "Briefing refresh",
  review_note: "Review note",
  document_upload: "Document processing",
  transcript: "Transcript processing",
};

export const CREDIT_ACTION_LABELS: Record<CreditFeature, string> = {
  chat: "Ask AI Copilot",
  meeting_brief: "Generate meeting brief",
  draft_email: "Generate draft",
  digest: "Generate briefing",
  review_note: "Generate review note",
  document_upload: "Process document",
  transcript: "Process transcript",
};

const BACKEND_COST_LABELS: Record<string, string> = {
  chat: "AI Copilot question",
  report: "Meeting brief",
  pdf_analysis: "Document analysis",
  draft_email: "Draft email",
  digest: "Briefing generation",
  review_note: "Review note",
  transcript_analysis: "Transcript analysis",
};

export function creditCostLabel(feature: string): string {
  return (
    BACKEND_COST_LABELS[feature] ??
    feature.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
  );
}

/** Prefer canonical backend keys, while tolerating common endpoint-era aliases. */
const COST_ALIASES: Record<CreditFeature, string[]> = {
  chat: ["chat", "ai_chat", "copilot"],
  meeting_brief: ["meeting_brief", "brief", "report"],
  draft_email: ["draft_email", "email_draft"],
  digest: ["digest", "digest_refresh", "morning_digest"],
  review_note: ["review_note", "client_review_note"],
  document_upload: ["document_upload", "upload", "ingest_document", "pdf_analysis"],
  transcript: ["transcript", "ingest_transcript", "transcript_analysis"],
};

export function getFeatureCost(
  costs: Record<string, number> | undefined,
  feature: CreditFeature
): number | undefined {
  if (!costs) return undefined;
  for (const key of COST_ALIASES[feature]) {
    const value = costs[key];
    if (Number.isFinite(value) && value >= 0) return value;
  }
  return undefined;
}

export function creditWarningLevel(remaining: number): 50 | 20 | 10 | 5 | 1 | 0 | null {
  if (remaining <= 0) return 0;
  if (remaining <= 1) return 1;
  if (remaining <= 5) return 5;
  if (remaining <= 10) return 10;
  if (remaining <= 20) return 20;
  if (remaining <= 50) return 50;
  return null;
}
