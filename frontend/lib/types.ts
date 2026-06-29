// Shared domain types mirrored from the backend Pydantic models.
// Keep in sync with backend/app/routers/*.py response models.

export type AlertType =
  | "DEADLINE"
  | "OPPORTUNITY"
  | "COMPLIANCE"
  | "REVIEW_OVERDUE"
  | "FOLLOW_UP";

export type AlertPriority = "HIGH" | "MEDIUM" | "LOW";

export type AlertStatus = "PENDING" | "COMPLETED";

export interface Alert {
  id: string;
  client_id: string;
  client_name: string;
  trigger_date: string;
  type: AlertType | string;
  priority: AlertPriority | string;
  title: string | null;
  description: string | null;
  status: AlertStatus | string;
}

export interface PulseData {
  alerts: Alert[];
  total: number;
  high_risk: number;
  deadlines: number;
  client_count: number;
  overdue_follow_ups?: Alert[];
}

export interface Client {
  id: string;
  full_name: string;
  last_review_date?: string | null;
  total_assets?: number | null;
  risk_score?: number | null;
  retirement_target_age?: number | null;
  cash_savings?: number | null;
  open_alert_count?: number;
}

export interface PlanningCompleteness {
  score: number;
  missing: string[];
}

export interface AtRiskScore {
  score: number;
  level: string;
  rationale: string;
}

export interface NextBestAction {
  action: string;
  reason: string;
  priority: string;
}

export interface ClientDetail extends Client {
  raw_profile_json?: Record<string, unknown> | null;
  pending_alerts: Alert[];
  overdue_follow_ups: Alert[];
  document_count: number;
  summary?: string | null;
  planning_completeness?: PlanningCompleteness | null;
  at_risk?: AtRiskScore | null;
  next_best_actions?: NextBestAction[];
}

export interface DigestResponse {
  digest: string;
  generated_at: string;
}

export interface BookAnalytics {
  clients_total: number;
  total_aum: number;
  average_risk_score: number | null;
  reviews_overdue: number;
}

// Partial edit of a client's extracted profile fields. Omitted fields are left
// untouched by the backend; an explicit null clears an optional field.
export interface ClientUpdateInput {
  full_name?: string;
  retirement_target_age?: number | null;
  risk_score?: number | null;
  total_assets?: number | null;
  cash_savings?: number | null;
  last_review_date?: string | null;
}

export interface ChatSource {
  ref?: number;
  content: string;
  client_name: string;
  doc_type: string;
  date: string;
  relevance?: number;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
}

export interface BriefResponse {
  brief: string;
  talking_points: string[];
  sources?: ChatSource[];
}

export interface DraftEmailResponse {
  draft: string;
  subject?: string | null;
}

export type DraftEmailSource =
  | { type: "alert"; alertId: string }
  | { type: "brief"; clientId: string; context: string; talkingPoints?: string[] };

export interface StoredDocument {
  id: string;
  filename: string;
  content_hash: string;
  file_size_bytes: number | null;
  uploaded_at: string;
  processing_error?: string | null;
}
