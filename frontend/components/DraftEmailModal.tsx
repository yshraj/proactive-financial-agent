import React, { useEffect, useMemo, useState } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import { AiBadge, AiThinkingCard, AiTrustFooter } from "./ai";
import { Modal } from "./ui/Modal";
import { Button, buttonClassName } from "./ui/Button";
import { ErrorState } from "./ui/ErrorState";
import { useToast } from "./ui/Toast";
import { useDraftEmail, useUpdateAlertStatus } from "../hooks/useApi";
import { aiErrorMessage } from "../lib/ai";
import { isSyntheticAlert } from "../lib/labels";
import type { DraftEmailSource } from "../lib/types";

const DRAFT_STEPS = [
  "Reviewing client context and alert details",
  "Drafting a professional client email",
  "Applying UK adviser tone and compliance guardrails",
];

type DraftEmailModalProps = {
  source: DraftEmailSource | null;
  onClose: () => void;
  onMarkDone?: (alertId: string) => void;
};

export default function DraftEmailModal({
  source,
  onClose,
  onMarkDone,
}: DraftEmailModalProps) {
  const { notify } = useToast();
  const [copied, setCopied] = useState(false);
  const draftQuery = useDraftEmail(source);
  const updateStatus = useUpdateAlertStatus();

  const alertId = source?.type === "alert" ? source.alertId : null;
  const canMarkDone =
    alertId != null && !isSyntheticAlert(alertId) && !!onMarkDone;

  useEffect(() => {
    setCopied(false);
  }, [source]);

  const draft = draftQuery.data?.draft;
  const subject = draftQuery.data?.subject;

  const mailtoHref = useMemo(() => {
    if (!draft) return null;
    const params = new URLSearchParams();
    if (subject) params.set("subject", subject);
    params.set("body", draft);
    return `mailto:?${params.toString()}`;
  }, [draft, subject]);

  const handleCopy = async () => {
    if (!draft) return;
    const text = subject ? `Subject: ${subject}\n\n${draft}` : draft;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      notify("Draft copied to clipboard", "success");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      notify("Couldn't copy to clipboard", "error");
    }
  };

  const handleMarkDone = () => {
    if (!alertId || !onMarkDone) return;
    updateStatus.mutate(
      { alertId, status: "COMPLETED" },
      {
        onSuccess: () => {
          notify("Marked as done", "success");
          onMarkDone(alertId);
          onClose();
        },
        onError: (e) => notify(e.message, "error"),
      }
    );
  };

  const title =
    source?.type === "brief" ? "Follow-up email draft" : "Client email draft";

  return (
    <Modal
      open={source != null}
      onClose={onClose}
      title={title}
      footer={
        <>
          {canMarkDone && (
            <Button
              variant="secondary"
              onClick={handleMarkDone}
              loading={updateStatus.isPending}
              className="border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
            >
              Mark as done
            </Button>
          )}
          <Button variant="secondary" onClick={onClose} data-testid="modal-footer-close">
            Close
          </Button>
          {draft && (
            <Button
              variant="secondary"
              onClick={() => draftQuery.refetch()}
              leftIcon={<RefreshCw className="h-4 w-4" aria-hidden />}
            >
              Regenerate
            </Button>
          )}
          {mailtoHref && (
            <a
              href={mailtoHref}
              className={buttonClassName("secondary", "md")}
            >
              <ExternalLink className="h-4 w-4" aria-hidden />
              Open in email client
            </a>
          )}
          {draft && (
            <Button onClick={handleCopy}>
              {copied ? "Copied" : "Copy to clipboard"}
            </Button>
          )}
        </>
      }
    >
      {draftQuery.isLoading && (
        <AiThinkingCard title="Drafting your email" steps={DRAFT_STEPS} compact={false} />
      )}
      {draftQuery.isError && (
        <ErrorState
          title="Couldn't generate the draft"
          message={aiErrorMessage(draftQuery.error, "draft")}
          onRetry={() => draftQuery.refetch()}
        />
      )}
      {draft && !draftQuery.isLoading && (
        <div>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <AiBadge label="Draft email" />
          </div>
          {subject && (
            <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50/80 px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
                Subject line
              </p>
              <p className="mt-1 text-sm font-medium text-slate-900">{subject}</p>
            </div>
          )}
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-800">
            {draft}
          </pre>
          <AiTrustFooter
            compact
            disclaimer="Review and personalise before sending. Not regulated advice — your firm remains responsible for client communications."
          />
        </div>
      )}
    </Modal>
  );
}
