import React from "react";
import {
  TrendingUp,
  AlertTriangle,
  ClipboardCheck,
  Clock,
  Mail,
} from "lucide-react";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { alertTypeLabel } from "../lib/labels";
import type { AlertType } from "../lib/types";

export interface AlertCardProps {
  type: AlertType;
  priority: "HIGH" | "MEDIUM" | "LOW";
  title: string;
  description: string;
  clientName?: string;
  onDraftEmail?: () => void;
}

const ICONS: Record<string, React.ReactNode> = {
  OPPORTUNITY: <TrendingUp className="h-4 w-4 text-emerald-600" aria-hidden />,
  REVIEW_OVERDUE: <ClipboardCheck className="h-4 w-4 text-violet-600" aria-hidden />,
  FOLLOW_UP: <Clock className="h-4 w-4 text-slate-500" aria-hidden />,
  DEADLINE: <AlertTriangle className="h-4 w-4 text-amber-600" aria-hidden />,
  COMPLIANCE: <AlertTriangle className="h-4 w-4 text-indigo-600" aria-hidden />,
};

export default function AlertCard({
  type,
  priority,
  title,
  description,
  clientName,
  onDraftEmail,
}: AlertCardProps) {
  return (
    <article className="flex flex-col rounded-xl border border-gray-200 bg-white p-5 shadow-xs transition-shadow hover:shadow-card-hover">
      <div className="mb-3 flex items-center gap-2">
        {ICONS[type] ?? ICONS.DEADLINE}
        <span className="ui-label">{alertTypeLabel(type)}</span>
        {priority === "HIGH" && (
          <Badge className="ml-auto bg-red-100 text-red-700">High</Badge>
        )}
      </div>
      <h3 className="mb-1 text-sm font-semibold text-gray-900">
        {title || "Alert"}
      </h3>
      {clientName && <p className="mb-2 text-sm text-gray-500">{clientName}</p>}
      <p className="mb-4 line-clamp-2 text-sm text-gray-600">
        {description || "No description."}
      </p>
      {onDraftEmail && (
        <Button
          size="sm"
          className="mt-auto self-start"
          leftIcon={<Mail className="h-4 w-4" aria-hidden />}
          onClick={onDraftEmail}
        >
          Draft email
        </Button>
      )}
    </article>
  );
}
