import { Button, ButtonLink, Modal } from "@/components/ui";

export function CreditHardStopModal({
  open,
  balanceUnavailable = false,
  required,
  remaining,
  used,
  canRequest,
  contactEmail,
  onRequest,
  onClose,
}: {
  open: boolean;
  balanceUnavailable?: boolean;
  required?: number;
  remaining?: number;
  used?: number;
  canRequest: boolean;
  contactEmail?: string;
  onRequest: () => void;
  onClose: () => void;
}) {
  const title = balanceUnavailable
    ? "AI credit balance unavailable"
    : remaining === 0
      ? "You’re out of AI credits"
      : "Not enough AI credits";
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          {canRequest && <Button onClick={onRequest}>Request more credits</Button>}
          {!canRequest && contactEmail && (
            <a className="text-sm font-medium text-brand-700 underline" href={`mailto:${contactEmail}`}>
              Contact {contactEmail}
            </a>
          )}
          <ButtonLink href="/settings#credit-history" variant="secondary" onClick={onClose}>
            View history
          </ButtonLink>
          <Button variant="secondary" onClick={onClose}>Close</Button>
        </>
      }
    >
      <p className="text-sm leading-relaxed text-slate-600">
        {balanceUnavailable
          ? "The balance could not be confirmed, so this paid-model AI action was not started."
          : required != null && remaining != null
            ? `This paid-model AI action requires ${required} credit${required === 1 ? "" : "s"}, but ${remaining} remain${remaining === 1 ? "s" : ""}.`
            : "There are not enough credits to start this paid-model AI action."}
      </p>
      {(remaining != null || used != null) && (
        <dl className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 p-3">
            <dt className="text-xs text-slate-500">Remaining</dt>
            <dd className="mt-1 text-base font-semibold text-slate-900">{remaining ?? "Unavailable"}</dd>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <dt className="text-xs text-slate-500">Total used</dt>
            <dd className="mt-1 text-base font-semibold text-slate-900">{used ?? "Unavailable"}</dd>
          </div>
        </dl>
      )}
      <p className="mt-4 text-xs leading-relaxed text-slate-500">
        Existing work is safe and remains available. Only new paid-model AI actions are
        blocked. Credits do not renew automatically.
      </p>
    </Modal>
  );
}
