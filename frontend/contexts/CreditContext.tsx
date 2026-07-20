import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import {
  type CreditErrorDetail,
  type CreditFeature,
  type CreditSummary,
  getFeatureCost,
} from "@/lib/credits";
import { useCreditSummary } from "@/hooks/useCreditsApi";
import { creditQueryKeys } from "@/hooks/useCreditsApi";
import { useToast } from "@/components/ui";
import {
  CreditConfirmModal,
  CreditContactModal,
  CreditHardStopModal,
} from "@/components/credits";

interface PendingAction {
  feature: CreditFeature;
  cost: number;
  key: string;
  run: () => Promise<unknown>;
}

interface HardStopState {
  kind: "insufficient" | "unavailable";
  required?: number;
  remaining?: number;
  contactAvailable?: boolean;
}

interface CreditContextValue {
  summary?: CreditSummary;
  isLoading: boolean;
  isError: boolean;
  activeFeature: CreditFeature | null;
  activeCost?: number;
  getCost: (feature: CreditFeature) => number | undefined;
  requestAction: (
    feature: CreditFeature,
    action: () => Promise<unknown>,
    actionKey?: string
  ) => void;
  openContact: () => void;
  refetch: () => Promise<unknown>;
}

const CreditContext = createContext<CreditContextValue | null>(null);

export function CreditProvider({ children }: { children: React.ReactNode }) {
  const query = useCreditSummary();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [hardStop, setHardStop] = useState<HardStopState | null>(null);
  const [contactOpen, setContactOpen] = useState(false);
  const [contactRequestOverride, setContactRequestOverride] = useState(false);
  const [active, setActive] = useState<{ feature: CreditFeature; cost: number } | null>(null);
  const lockedActions = useRef(new Set<string>());
  const scheduledActions = useRef(new Set<string>());
  const executionChain = useRef(Promise.resolve());

  const getCost = useCallback(
    (feature: CreditFeature) => getFeatureCost(query.data?.costs, feature),
    [query.data?.costs]
  );

  const execute = useCallback(
    async (action: PendingAction) => {
      setPending((current) => current.filter((item) => item !== action));
      const before =
        queryClient.getQueryData<CreditSummary>(creditQueryKeys.summary) ?? query.data;
      if (!before) {
        lockedActions.current.delete(action.key);
        setHardStop({ kind: "unavailable" });
        return;
      }
      if (before.remaining < action.cost) {
        lockedActions.current.delete(action.key);
        setHardStop({
          kind: "insufficient",
          required: action.cost,
          remaining: before.remaining,
        });
        return;
      }
      setActive({ feature: action.feature, cost: action.cost });
      try {
        await action.run();
        const refreshed = await query.refetch();
        if (refreshed.data) {
          const charged = Math.max(0, refreshed.data.used - before.used);
          notify(
            charged === 0
              ? `No AI credits used. ${refreshed.data.remaining} remaining.`
              : `${charged} AI credit${charged === 1 ? "" : "s"} used. ${refreshed.data.remaining} remaining.`,
            "success"
          );
        }
      } catch (error) {
        await query.refetch();
        const detail =
          error instanceof ApiError && error.detail && typeof error.detail === "object"
            ? (error.detail as CreditErrorDetail)
            : null;
        if (detail?.error === "insufficient_credits") {
          setHardStop({
            kind: "insufficient",
            required: detail.required,
            remaining: detail.remaining,
            contactAvailable: detail.contact_available,
          });
        } else if (detail?.error === "credit_balance_unavailable" || (error instanceof ApiError && error.status === 503)) {
          setHardStop({ kind: "unavailable" });
        }
      } finally {
        lockedActions.current.delete(action.key);
        setActive(null);
      }
    },
    [notify, query, queryClient]
  );

  const schedule = useCallback((action: PendingAction) => {
    if (scheduledActions.current.has(action.key)) return;
    scheduledActions.current.add(action.key);
    executionChain.current = executionChain.current
      .then(() => execute(action))
      .finally(() => scheduledActions.current.delete(action.key));
  }, [execute]);

  const requestAction = useCallback(
    (
      feature: CreditFeature,
      run: () => Promise<unknown>,
      actionKey: string = feature
    ) => {
      const cost = getFeatureCost(query.data?.costs, feature);
      if (!query.data || cost == null) {
        setHardStop({ kind: "unavailable" });
        return;
      }
      if (query.data.remaining < cost || query.data.remaining === 0) {
        setHardStop({
          kind: "insufficient",
          required: cost,
          remaining: query.data.remaining,
        });
        return;
      }
      if (lockedActions.current.has(actionKey)) {
        return;
      }
      lockedActions.current.add(actionKey);
      const action = { feature, cost, key: actionKey, run };
      if (cost >= 3) setPending((current) => [...current, action]);
      else schedule(action);
    },
    [query.data, schedule]
  );

  const value = useMemo<CreditContextValue>(
    () => ({
      summary: query.data,
      isLoading: query.isLoading,
      isError: query.isError,
      activeFeature: active?.feature ?? null,
      activeCost: active?.cost,
      getCost,
      requestAction,
      openContact: () => {
        setContactRequestOverride(false);
        setContactOpen(true);
      },
      refetch: query.refetch,
    }),
    [active, getCost, query.data, query.isError, query.isLoading, query.refetch, requestAction]
  );

  return (
    <CreditContext.Provider value={value}>
      {children}
      <div className="sr-only" role="status" aria-live="polite">
        {active ? `Using ${active.cost} AI credits. Charged only when complete.` : ""}
      </div>
      {pending[0] && query.data && !active && (
        <CreditConfirmModal
          open
          feature={pending[0].feature}
          cost={pending[0].cost}
          remaining={query.data.remaining}
          onConfirm={() => schedule(pending[0])}
          onClose={() => {
            lockedActions.current.delete(pending[0].key);
            setPending((current) => current.slice(1));
          }}
        />
      )}
      <CreditHardStopModal
        open={hardStop != null}
        balanceUnavailable={hardStop?.kind === "unavailable"}
        required={hardStop?.required}
        remaining={hardStop?.remaining ?? query.data?.remaining}
        used={query.data?.used}
        canRequest={
          hardStop?.contactAvailable ?? query.data?.contact.request_enabled ?? false
        }
        contactEmail={query.data?.contact.email}
        onRequest={() => {
          setContactRequestOverride(hardStop?.contactAvailable ?? false);
          setHardStop(null);
          setContactOpen(true);
        }}
        onClose={() => setHardStop(null)}
      />
      <CreditContactModal
        open={contactOpen}
        email={query.data?.contact.email}
        requestEnabled={
          contactRequestOverride || query.data?.contact.request_enabled || false
        }
        onClose={() => setContactOpen(false)}
      />
    </CreditContext.Provider>
  );
}

export function useCredits() {
  const context = useContext(CreditContext);
  if (!context) throw new Error("useCredits must be used within CreditProvider");
  return context;
}
