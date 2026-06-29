import { useState } from "react";
import { Modal, Button, useToast } from "./ui";
import { AiMarkdown } from "./ai";
import type { ReviewNoteResponse } from "../lib/types";

interface ReviewNoteModalProps {
  data?: ReviewNoteResponse;
  loading: boolean;
  onClose: () => void;
}

/** Shows a generated Consumer-Duty review note with a copy-to-clipboard action. */
export default function ReviewNoteModal({ data, loading, onClose }: ReviewNoteModalProps) {
  const { notify } = useToast();
  const [copied, setCopied] = useState(false);

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
      {loading || !data ? (
        <p className="text-sm text-slate-500" data-testid="review-note-loading">
          Generating review note…
        </p>
      ) : (
        <div data-testid="review-note-content">
          <AiMarkdown>{data.note}</AiMarkdown>
          <p className="mt-4 text-[11px] text-slate-400">
            {data.ai_generated ? "AI-generated draft" : "Generated from your records"} — confirm before filing.
          </p>
        </div>
      )}
    </Modal>
  );
}
