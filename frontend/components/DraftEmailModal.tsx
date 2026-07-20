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
import { ActionCost } from "./credits";
import { useCredits } from "../contexts/CreditContext";

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
  const [hasRequested, setHasRequested] = useState(false);
  const [generationError, setGenerationError] = useState<unknown>(null);
  const draftQuery = useDraftEmail(source, false);
  const { requestAction, activeFeature, activeCost, getCost } = useCredits();
  const updateStatus = useUpdateAlertStatus();

  const alertId = source?.type === "alert" ? source.alertId : null;
  const canMarkDone =
    alertId != null && !isSyntheticAlert(alertId) && !!onMarkDone;

  useEffect(() => {
    setCopied(false);
    setHasRequested(false);
    setGenerationError(null);
  }, [source]);

  const generate = (refresh = false) => {
    requestAction("draft_email", async () => {
      setHasRequested(true);
      setGenerationError(null);
      try {
        if (refresh) return await draftQuery.regenerate();
        const result = await draftQuery.refetch();
        if (result.error) throw result.error;
        return result.data;
      } catch (error) {
        setGenerationError(error);
        throw error;
      }
    });
  };

  const draft = hasRequested ? draftQuery.data?.draft : undefined;
  const subject = hasRequested ? draftQuery.data?.subject : undefined;
  const draftCost = getCost("draft_email");

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
              onClick={() => generate(true)}
              disabled={activeFeature === "draft_email"}
              leftIcon={<RefreshCw className="h-4 w-4" aria-hidden />}
              data-testid="regenerate-draft-button"
            >
              Regenerate · {draftCost ?? "—"} credit{draftCost === 1 ? "" : "s"}
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
      <ActionCost feature="draft_email" className="mb-3 block" />
      {!hasRequested && activeFeature !== "draft_email" && (
        <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-5 text-center">
          <p className="text-sm text-slate-600">
            Review the cost before creating a client-ready email draft. Opening this preview
            has not used any credits.
          </p>
          <Button
            className="mt-4"
            onClick={() => generate()}
            data-testid="generate-draft-button"
          >
            Generate draft · {draftCost ?? "—"} credit{draftCost === 1 ? "" : "s"}
          </Button>
        </div>
      )}
      {(draftQuery.isFetching || activeFeature === "draft_email") && (
        <AiThinkingCard
          title={
            activeFeature === "draft_email" && activeCost != null
              ? `Drafting your email · using ${activeCost} credits`
              : "Drafting your email"
          }
          steps={DRAFT_STEPS}
          compact={false}
        />
      )}
      {(generationError || draftQuery.isError) && (
        <ErrorState
          title="Couldn't generate the draft"
          message={aiErrorMessage(generationError ?? draftQuery.error, "draft")}
          onRetry={() => generate()}
        />
      )}
      {draft && !generationError && !draftQuery.isFetching && activeFeature !== "draft_email" && (
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
