import { useState } from "react";
import { Modal, Button, ErrorState, useToast } from "./ui";
import { AiMarkdown } from "./ai";
import type { ReviewNoteResponse } from "../lib/types";
import { ActionCost } from "./credits";
import { useCredits } from "../contexts/CreditContext";

interface ReviewNoteModalProps {
  data?: ReviewNoteResponse;
  loading: boolean;
  error?: unknown;
  onRetry: () => void;
  onClose: () => void;
}

/** Shows a generated Consumer-Duty review note with a copy-to-clipboard action. */
export default function ReviewNoteModal({ data, loading, error, onRetry, onClose }: ReviewNoteModalProps) {
  const { notify } = useToast();
  const [copied, setCopied] = useState(false);
  const { activeFeature, activeCost } = useCredits();

  const copy = async () => {
    if (!data?.note) return;
    try {
      await navigator.clipboard.writeText(data.note);
      setCopied(true);
      notify("Review note copied to clipboard", "success");
    } catch {
      notify("Couldn't copy to clipboard", "error");
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Client review note"
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          <Button onClick={copy} disabled={!data?.note} data-testid="copy-review-note">
            {copied ? "Copied" : "Copy to clipboard"}
          </Button>
        </>
      }
    >
      <ActionCost feature="review_note" className="mb-3 block" />
      {error ? (
        <ErrorState
          title="Couldn't generate the review note"
          message={error instanceof Error ? error.message : "Generation failed. No credits used."}
          onRetry={onRetry}
        />
      ) : loading || !data ? (
        <p className="text-sm text-slate-500" data-testid="review-note-loading">
          {activeFeature === "review_note" && activeCost != null
            ? `Generating review note… Using ${activeCost} credits, charged only when complete.`
            : "Preparing review note… Credits are charged only when complete."}
        </p>
      ) : (
        <div data-testid="review-note-content">
          <AiMarkdown>{data.note}</AiMarkdown>
          <p className="mt-4 text-[11px] text-slate-500">
            {data.ai_generated ? "AI-generated draft" : "Generated from your records"} — confirm before filing.
          </p>
        </div>
      )}
    </Modal>
  );
}
