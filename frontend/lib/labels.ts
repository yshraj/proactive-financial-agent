// Single source of truth for human-readable labels and badge styling.
// Fixes the cross-page inconsistency where Alerts showed raw enums (FOLLOW_UP)
// while the Dashboard humanized them.
import type { AlertPriority, AlertType } from "./types";

export const ALERT_TYPE_LABEL: Record<string, string> = {
  DEADLINE: "Deadline",
  OPPORTUNITY: "Opportunity",
  COMPLIANCE: "Compliance",
  REVIEW_OVERDUE: "Review overdue",
  FOLLOW_UP: "Waiting on client",
};

export function alertTypeLabel(type: string): string {
  return ALERT_TYPE_LABEL[type] ?? type;
}

export const ALERT_TYPE_BADGE: Record<string, string> = {
  DEADLINE: "bg-amber-100 text-amber-800",
  OPPORTUNITY: "bg-emerald-100 text-emerald-800",
  COMPLIANCE: "bg-indigo-100 text-indigo-800",
  REVIEW_OVERDUE: "bg-violet-100 text-violet-800",
  FOLLOW_UP: "bg-slate-100 text-slate-700",
};

export function alertTypeBadge(type: string): string {
  return ALERT_TYPE_BADGE[type] ?? "bg-gray-100 text-gray-700";
}

export const PRIORITY_BADGE: Record<string, string> = {
  HIGH: "bg-red-100 text-red-700",
  MEDIUM: "bg-brand-100 text-brand-700",
  LOW: "bg-gray-100 text-gray-600",
};

export function priorityBadge(priority: string): string {
  return PRIORITY_BADGE[priority] ?? "bg-gray-100 text-gray-600";
}

export function priorityLabel(priority: AlertPriority | string): string {
  if (!priority) return "";
  return priority.charAt(0) + priority.slice(1).toLowerCase();
}

// Type guard helpers
export const isReviewOverdue = (type: string): type is AlertType =>
  type === "REVIEW_OVERDUE";
export const isSyntheticAlert = (id: string): boolean =>
  id.startsWith("review-overdue-");
