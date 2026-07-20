import { Button, Modal } from "@/components/ui";
import type { CreditFeature } from "@/lib/credits";
import { CREDIT_ACTION_LABELS, CREDIT_FEATURE_LABELS } from "@/lib/credits";

export function CreditConfirmModal({
  open,
  feature,
  cost,
  remaining,
  onConfirm,
  onClose,
}: {
  open: boolean;
  feature: CreditFeature;
  cost: number;
  remaining: number;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Use ${cost} AI credits?`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={onConfirm} data-testid="credit-confirm">
            {CREDIT_ACTION_LABELS[feature]} · {cost} credit{cost === 1 ? "" : "s"}
          </Button>
        </>
      }
    >
      <p className="text-sm leading-relaxed text-slate-600">
        {CREDIT_FEATURE_LABELS[feature]} uses exactly {cost} credit{cost === 1 ? "" : "s"}.
        You will have {Math.max(0, remaining - cost)} remaining when it completes.
      </p>
      <p className="mt-3 text-xs text-slate-500">
        Credits are charged only when generation completes. Cancelling or a failed generation
        uses no credits.
      </p>
    </Modal>
  );
}
