import { FileText, Mail, Sparkles } from "lucide-react";
import { Button, ButtonLink, Card } from "./ui";
import { briefForClient, chatWithQuery, DEMO_COPILOT_QUERY } from "../lib/demo";
import { formatDate } from "../lib/format";
import { alertTypeLabel, isReviewOverdue } from "../lib/labels";
import type { Alert } from "../lib/types";

type DemoSpotlightProps = {
  alert: Alert;
  onDraftEmail: (alertId: string) => void;
};

/** Highlights the #1 priority client for one-click demo actions. */
export function DemoSpotlight({ alert, onDraftEmail }: DemoSpotlightProps) {
  const title = isReviewOverdue(alert.type)
    ? "Annual review overdue"
    : alert.title || alertTypeLabel(alert.type);

  return (
    <Card
      className="mb-8 animate-fade-in overflow-hidden border-brand-200 bg-gradient-to-br from-brand-50/90 to-white"
      data-testid="demo-spotlight"
    >
      <div className="flex flex-col gap-5 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-600">
            Top priority today
          </p>
          <h3 className="mt-1 text-xl font-semibold tracking-tight text-slate-950">
            {alert.client_name}
          </h3>
          <p className="mt-2 text-sm text-slate-600">
            {title}
            {!isReviewOverdue(alert.type) && alert.trigger_date && (
              <span className="text-slate-500"> · due {formatDate(alert.trigger_date)}</span>
            )}
          </p>
          {alert.description && (
            <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-slate-500">
              {alert.description}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <ButtonLink
            href={briefForClient(alert.client_id)}
            size="md"
            leftIcon={<FileText className="h-4 w-4" aria-hidden />}
            data-testid="demo-spotlight-prepare"
          >
            Prepare brief
          </ButtonLink>
          <ButtonLink
            href={chatWithQuery(DEMO_COPILOT_QUERY, alert.client_id)}
            variant="secondary"
            size="md"
            leftIcon={<Sparkles className="h-4 w-4" aria-hidden />}
          >
            Ask Copilot
          </ButtonLink>
          <Button
            variant="secondary"
            size="md"
            leftIcon={<Mail className="h-4 w-4" aria-hidden />}
            onClick={() => onDraftEmail(alert.id)}
          >
            Preview email draft
          </Button>
        </div>
      </div>
    </Card>
  );
}
