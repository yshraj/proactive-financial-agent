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
}

export interface ChatSource {
  content: string;
  client_name: string;
  doc_type: string;
  date: string;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
}

export interface BriefResponse {
  brief: string;
  talking_points: string[];
}

export interface StoredDocument {
  id: string;
  filename: string;
  content_hash: string;
  file_size_bytes: number | null;
  uploaded_at: string;
  processing_error?: string | null;
}
