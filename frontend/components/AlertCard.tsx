import React, { memo, useCallback } from "react";
import {
  TrendingUp,
  AlertTriangle,
  ClipboardCheck,
  Clock,
  Mail,
  FileText,
} from "lucide-react";
import { Button, ButtonLink } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { alertTypeLabel } from "../lib/labels";
import type { AlertType } from "../lib/types";

export interface AlertCardProps {
  type: AlertType;
  priority: "HIGH" | "MEDIUM" | "LOW";
  title: string;
  description: string;
  clientName?: string;
  prepareHref?: string;
  /** @deprecated Prefer draftAlertId + onDraftAlert for stable memoization */
  onDraftEmail?: () => void;
  draftAlertId?: string;
  onDraftAlert?: (alertId: string) => void;
}

const ICONS: Record<string, React.ReactNode> = {
  OPPORTUNITY: <TrendingUp className="h-4 w-4 text-emerald-600" aria-hidden />,
  REVIEW_OVERDUE: <ClipboardCheck className="h-4 w-4 text-violet-600" aria-hidden />,
  FOLLOW_UP: <Clock className="h-4 w-4 text-slate-500" aria-hidden />,
  DEADLINE: <AlertTriangle className="h-4 w-4 text-amber-600" aria-hidden />,
  COMPLIANCE: <AlertTriangle className="h-4 w-4 text-indigo-600" aria-hidden />,
};

function AlertCard({
  type,
  priority,
  title,
  description,
  clientName,
  prepareHref,
  onDraftEmail,
  draftAlertId,
  onDraftAlert,
}: AlertCardProps) {
  const handleDraft = useCallback(() => {
    if (draftAlertId && onDraftAlert) {
      onDraftAlert(draftAlertId);
    } else {
      onDraftEmail?.();
    }
  }, [draftAlertId, onDraftAlert, onDraftEmail]);

  const showDraft = Boolean(onDraftEmail || (draftAlertId && onDraftAlert));

  return (
    <article className="flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-xs transition-shadow duration-200 hover:shadow-card">
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-50 ring-1 ring-slate-100">
          {ICONS[type] ?? ICONS.DEADLINE}
        </span>
        <span className="ui-label">{alertTypeLabel(type)}</span>
        {priority === "HIGH" && (
          <Badge className="ml-auto bg-red-100 text-red-700">High</Badge>
        )}
      </div>
      <h3 className="mb-1 text-sm font-semibold text-slate-950">
        {title || "Alert"}
      </h3>
      {clientName && <p className="mb-2 text-sm text-slate-500">{clientName}</p>}
      <p className="mb-4 line-clamp-2 flex-1 text-sm leading-6 text-slate-600">
        {description || "No description."}
      </p>
      {(prepareHref || showDraft) && (
        <div className="mt-auto flex flex-wrap gap-2">
          {prepareHref && (
            <ButtonLink
              href={prepareHref}
              size="sm"
              variant="secondary"
              leftIcon={<FileText className="h-4 w-4" aria-hidden />}
            >
              Prepare
            </ButtonLink>
          )}
          {showDraft && (
            <Button
              size="sm"
              leftIcon={<Mail className="h-4 w-4" aria-hidden />}
              onClick={handleDraft}
            >
              Draft email
            </Button>
          )}
        </div>
      )}
    </article>
  );
}

export default memo(AlertCard);
