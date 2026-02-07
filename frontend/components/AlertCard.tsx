import React from "react";

export type AlertType = "DEADLINE" | "OPPORTUNITY" | "COMPLIANCE" | "REVIEW_OVERDUE" | "FOLLOW_UP";

export type AlertCardProps = {
  type: AlertType;
  priority: "HIGH" | "MEDIUM" | "LOW";
  title: string;
  description: string;
  clientName?: string;
  onDraftEmail?: () => void;
};

/**
 * Single Pulse alert – risk or opportunity, title, body, Draft Email action.
 * Styled with Tailwind to match the dashboard.
 */
export default function AlertCard({
  type,
  priority,
  title,
  description,
  clientName,
  onDraftEmail,
}: AlertCardProps) {
  const isOpportunity = type === "OPPORTUNITY";
  const isReviewOverdue = type === "REVIEW_OVERDUE";
  const isFollowUp = type === "FOLLOW_UP";
  const icon = isOpportunity ? "💰" : isReviewOverdue ? "📋" : isFollowUp ? "📌" : "⚠️";
  const typeLabel = isOpportunity ? "Opportunity" : isReviewOverdue ? "Review overdue" : isFollowUp ? "Waiting on client" : "Risk";

  return (
    <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-card transition-shadow hover:shadow-card-hover">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-lg" aria-hidden>
          {icon}
        </span>
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">{typeLabel}</span>
        {priority === "HIGH" && (
          <span className="rounded-md bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">High</span>
        )}
      </div>
      <h3 className="mb-1 text-base font-semibold text-gray-900">{title || "Alert"}</h3>
      {clientName && <p className="mb-2 text-sm text-gray-500">{clientName}</p>}
      <p className="mb-4 line-clamp-2 text-sm text-gray-600">{description || "No description."}</p>
      {onDraftEmail && (
        <button
          type="button"
          onClick={onDraftEmail}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-sky-500"
        >
          Draft Email
        </button>
      )}
    </article>
  );
}
