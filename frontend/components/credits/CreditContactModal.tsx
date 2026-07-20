import { useEffect, useState } from "react";
import { Button, Modal, useToast } from "@/components/ui";
import { useRequestCredits } from "@/hooks/useCreditsApi";

export function CreditContactModal({
  open,
  email,
  requestEnabled,
  onClose,
}: {
  open: boolean;
  email?: string;
  requestEnabled: boolean;
  onClose: () => void;
}) {
  const [message, setMessage] = useState("");
  const request = useRequestCredits();
  const { notify } = useToast();
  useEffect(() => {
    if (!open) setMessage("");
  }, [open]);

  const submit = () => {
    request.mutate(message.trim(), {
      onSuccess: () => {
        notify(
          "Request pending. The project owner will review it manually; your credit balance has not changed.",
          "success"
        );
        onClose();
      },
      onError: (error) => notify(error.message, "error"),
    });
  };

  return (
    <Modal
      open={open}
      onClose={() => !request.isPending && onClose()}
      title="Request more AI credits"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={request.isPending}>Close</Button>
          {requestEnabled && (
            <Button
              onClick={submit}
              loading={request.isPending}
              disabled={!message.trim()}
              data-testid="credit-request-submit"
            >
              Send request
            </Button>
          )}
        </>
      }
    >
      {requestEnabled ? (
        <>
          <label htmlFor="credit-request-message" className="ui-label mb-2 block">
            How do you use AI in this workspace?
          </label>
          <textarea
            id="credit-request-message"
            className="input min-h-[120px] py-3"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Add context for your request…"
            data-testid="credit-request-message"
          />
          <p className="mt-2 text-xs text-slate-500">
            The project owner will review this request manually. Sending it does not change
            your balance.
          </p>
        </>
      ) : (
        <p className="text-sm text-slate-600">
          Contact{" "}
          {email ? <a className="font-medium text-brand-700 underline" href={`mailto:${email}`}>{email}</a> : "support"}{" "}
          to request more credits.
        </p>
      )}
      {email && (
        <p className="mt-4 border-t border-slate-100 pt-4 text-xs text-slate-500">
          Prefer email?{" "}
          <a
            className="font-medium text-brand-700 underline"
            href={`mailto:${email}?subject=${encodeURIComponent("AI credit request")}`}
          >
            Contact the project owner
          </a>
          .
        </p>
      )}
    </Modal>
  );
}
