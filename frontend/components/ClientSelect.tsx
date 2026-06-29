import type { Client } from "@/lib/types";

type ClientSelectProps = {
  id: string;
  value: string;
  onChange: (clientId: string) => void;
  clients: Client[];
  isLoading?: boolean;
  disabled?: boolean;
  /** When true, prepends an empty "All clients" option (copilot scope). */
  allowAll?: boolean;
  allLabel?: string;
  loadingLabel?: string;
  emptyLabel?: string;
  className?: string;
  testId?: string;
};

/** Shared client dropdown used on Meeting Brief and AI Copilot pages. */
export default function ClientSelect({
  id,
  value,
  onChange,
  clients,
  isLoading = false,
  disabled = false,
  allowAll = false,
  allLabel = "All clients",
  loadingLabel = "Loading clients…",
  emptyLabel = "No clients yet",
  className = "input min-w-[200px] flex-1",
  testId,
}: ClientSelectProps) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled || isLoading || (!allowAll && clients.length === 0)}
      className={className}
      data-testid={testId}
    >
      {allowAll && <option value="">{allLabel}</option>}
      {isLoading && !allowAll && <option value="">{loadingLabel}</option>}
      {!isLoading && !allowAll && clients.length === 0 && (
        <option value="">{emptyLabel}</option>
      )}
      {clients.map((c) => (
        <option key={c.id} value={c.id}>
          {c.full_name}
        </option>
      ))}
    </select>
  );
}
