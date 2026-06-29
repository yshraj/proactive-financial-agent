import { useState } from "react";
import { Button, Modal, useToast } from "./ui";
import { useUpdateClient } from "../hooks/useApi";
import { errorMessage } from "../lib/api";
import type { ClientDetail, ClientUpdateInput } from "../lib/types";

interface EditClientModalProps {
  client: ClientDetail;
  onClose: () => void;
}

/** Parse a numeric input; blank becomes null (clears the field), invalid stays undefined. */
function toNumberOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  return Number.isNaN(n) ? null : n;
}

/**
 * Modal form for correcting a client's extracted profile fields.
 * Sends all editable fields; the backend validates and applies the update.
 */
export default function EditClientModal({ client, onClose }: EditClientModalProps) {
  const { notify } = useToast();
  const update = useUpdateClient(client.id);

  const [fullName, setFullName] = useState(client.full_name ?? "");
  const [totalAssets, setTotalAssets] = useState(
    client.total_assets != null ? String(client.total_assets) : ""
  );
  const [cashSavings, setCashSavings] = useState(
    client.cash_savings != null ? String(client.cash_savings) : ""
  );
  const [riskScore, setRiskScore] = useState(
    client.risk_score != null ? String(client.risk_score) : ""
  );
  const [retirementAge, setRetirementAge] = useState(
    client.retirement_target_age != null ? String(client.retirement_target_age) : ""
  );
  const [lastReview, setLastReview] = useState(client.last_review_date ?? "");

  const handleSave = () => {
    const payload: ClientUpdateInput = {
      full_name: fullName.trim(),
      total_assets: toNumberOrNull(totalAssets),
      cash_savings: toNumberOrNull(cashSavings),
      risk_score: toNumberOrNull(riskScore),
      retirement_target_age: toNumberOrNull(retirementAge),
      last_review_date: lastReview.trim() || null,
    };
    update.mutate(payload, {
      onSuccess: () => {
        notify("Client details updated.", "success");
        onClose();
      },
      onError: (e) => notify(errorMessage(e, "Couldn't update client."), "error"),
    });
  };

  const field = (
    label: string,
    input: React.ReactNode,
  ) => (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>
      {input}
    </label>
  );

  return (
    <Modal
      open
      onClose={() => !update.isPending && onClose()}
      title="Edit client details"
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={update.isPending}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            loading={update.isPending}
            disabled={!fullName.trim()}
            data-testid="save-client-button"
          >
            Save changes
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" data-testid="edit-client-form">
        <div className="sm:col-span-2">
          {field(
            "Full name",
            <input
              className="input"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              data-testid="edit-full-name"
            />
          )}
        </div>
        {field(
          "Total assets (£)",
          <input
            className="input"
            type="number"
            min="0"
            value={totalAssets}
            onChange={(e) => setTotalAssets(e.target.value)}
            data-testid="edit-total-assets"
          />
        )}
        {field(
          "Cash savings (£)",
          <input
            className="input"
            type="number"
            min="0"
            value={cashSavings}
            onChange={(e) => setCashSavings(e.target.value)}
          />
        )}
        {field(
          "Risk score (1–10)",
          <input
            className="input"
            type="number"
            min="1"
            max="10"
            value={riskScore}
            onChange={(e) => setRiskScore(e.target.value)}
          />
        )}
        {field(
          "Retirement target age",
          <input
            className="input"
            type="number"
            min="30"
            max="120"
            value={retirementAge}
            onChange={(e) => setRetirementAge(e.target.value)}
          />
        )}
        <div className="sm:col-span-2">
          {field(
            "Last review date",
            <input
              className="input"
              type="date"
              value={lastReview}
              onChange={(e) => setLastReview(e.target.value)}
            />
          )}
        </div>
      </div>
    </Modal>
  );
}
