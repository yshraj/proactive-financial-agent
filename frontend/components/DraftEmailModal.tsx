import React, { useEffect, useState } from "react";
import { Modal } from "./ui/Modal";
import { Button } from "./ui/Button";
import { ErrorState } from "./ui/ErrorState";
import { Skeleton } from "./ui/Skeleton";
import { useToast } from "./ui/Toast";
import { useDraftEmail, useUpdateAlertStatus } from "../hooks/useApi";
import { isSyntheticAlert } from "../lib/labels";

type DraftEmailModalProps = {
  alertId: string | null;
  onClose: () => void;
  onMarkDone?: (alertId: string) => void;
};

export default function DraftEmailModal({
  alertId,
  onClose,
  onMarkDone,
}: DraftEmailModalProps) {
  const { notify } = useToast();
  const [copied, setCopied] = useState(false);
  const draftQuery = useDraftEmail(alertId);
  const updateStatus = useUpdateAlertStatus();

  const canMarkDone =
    alertId != null && !isSyntheticAlert(alertId) && !!onMarkDone;

  useEffect(() => {
    setCopied(false);
  }, [alertId]);

  const handleCopy = async () => {
    const draft = draftQuery.data?.draft;
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draft);
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

  return (
    <Modal
      open={alertId != null}
      onClose={onClose}
      title="Email draft"
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
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          {draftQuery.data?.draft && (
            <Button onClick={handleCopy}>
              {copied ? "Copied" : "Copy to clipboard"}
            </Button>
          )}
        </>
      }
    >
      {draftQuery.isLoading && (
        <div className="space-y-2" aria-busy="true" aria-label="Generating draft">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      )}
      {draftQuery.isError && (
        <ErrorState
          title="Couldn't generate the draft"
          message={(draftQuery.error as Error)?.message}
          onRetry={() => draftQuery.refetch()}
        />
      )}
      {draftQuery.data?.draft && !draftQuery.isLoading && (
        <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-800">
          {draftQuery.data.draft}
        </pre>
      )}
    </Modal>
  );
}
