// React Query hooks wrapping the typed API client.
// Centralizes fetching, caching, dedup, retry and invalidation so pages
// don't hand-roll loading/error/data state.
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback } from "react";
import { api, ApiError } from "@/lib/api";
import { downloadExport, type ExportType } from "@/lib/export";
import { uploadDocument } from "@/lib/ingest";
import type {
  Alert,
  BriefResponse,
  ChatResponse,
  Client,
  ClientDetail,
  DigestResponse,
  DraftEmailResponse,
  DraftEmailSource,
  PulseData,
  StoredDocument,
} from "@/lib/types";

export const queryKeys = {
  pulse: (date: string) => ["pulse", date] as const,
  digest: (date: string) => ["digest", date] as const,
  completed: () => ["completed"] as const,
  clients: () => ["clients"] as const,
  clientDetail: (id: string) => ["client", id] as const,
  alerts: (params: Record<string, string>) => ["alerts", params] as const,
  documents: () => ["documents"] as const,
};

/** Prefetch client list on nav hover to warm cache before navigation. */
export function prefetchClients(qc: ReturnType<typeof useQueryClient>) {
  return qc.prefetchQuery({
    queryKey: queryKeys.clients(),
    queryFn: () => api.get<{ clients: Client[] }>("/api/monitor/clients"),
    staleTime: 5 * 60_000,
  });
}

export function usePulse(simulatedDate: string) {
  return useQuery({
    queryKey: queryKeys.pulse(simulatedDate),
    queryFn: () =>
      api.get<PulseData>(
        `/api/monitor/pulse?simulated_date=${encodeURIComponent(simulatedDate)}`
      ),
    enabled: !!simulatedDate,
  });
}

export function useCompleted() {
  return useQuery({
    queryKey: queryKeys.completed(),
    queryFn: () =>
      api.get<{ alerts: Alert[] }>("/api/monitor/completed?limit=10"),
  });
}

export function useClients() {
  return useQuery({
    queryKey: queryKeys.clients(),
    queryFn: () => api.get<{ clients: Client[] }>("/api/monitor/clients"),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  });
}

export function useAlerts(params: {
  simulated_date: string;
  days: number;
  type?: string;
  priority?: string;
  status?: string;
}) {
  const search = new URLSearchParams({
    simulated_date: params.simulated_date,
    days: String(params.days),
  });
  if (params.type && params.type !== "All") search.set("type", params.type);
  if (params.priority && params.priority !== "All")
    search.set("priority", params.priority);
  if (params.status && params.status !== "All")
    search.set("status", params.status);
  const key = Object.fromEntries(search.entries());
  return useQuery({
    queryKey: queryKeys.alerts(key),
    queryFn: () => api.get<{ alerts: Alert[] }>(`/api/monitor/alerts?${search}`),
    placeholderData: (prev) => prev,
  });
}

export function useDocuments() {
  return useQuery({
    queryKey: queryKeys.documents(),
    queryFn: () => api.get<StoredDocument[]>("/api/ingest/documents"),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  });
}

type AlertStatusVars = { alertId: string; status: string };

interface AlertStatusContext {
  prevPulse: [readonly unknown[], PulseData | undefined][];
  prevAlerts: [readonly unknown[], { alerts: Alert[] } | undefined][];
}

export function useUpdateAlertStatus() {
  const qc = useQueryClient();
  return useMutation<Alert, ApiError, AlertStatusVars, AlertStatusContext>({
    mutationFn: (vars) =>
      api.patch<Alert>(`/api/monitor/alerts/${encodeURIComponent(vars.alertId)}/status`, {
        status: vars.status,
      }),
    // Optimistically reflect the change so "Mark done" feels instant: drop the
    // alert from the dashboard pulse and flip its status in any alerts table.
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: ["pulse"] });
      await qc.cancelQueries({ queryKey: ["alerts"] });

      const prevPulse = qc.getQueriesData<PulseData>({ queryKey: ["pulse"] });
      const prevAlerts = qc.getQueriesData<{ alerts: Alert[] }>({ queryKey: ["alerts"] });

      const isDone = vars.status === "COMPLETED";

      qc.setQueriesData<PulseData>({ queryKey: ["pulse"] }, (old) =>
        old && isDone
          ? {
              ...old,
              alerts: old.alerts.filter((a) => a.id !== vars.alertId),
              overdue_follow_ups: old.overdue_follow_ups?.filter(
                (a) => a.id !== vars.alertId
              ),
            }
          : old
      );

      qc.setQueriesData<{ alerts: Alert[] }>({ queryKey: ["alerts"] }, (old) =>
        old
          ? {
              alerts: old.alerts.map((a) =>
                a.id === vars.alertId ? { ...a, status: vars.status } : a
              ),
            }
          : old
      );

      return { prevPulse, prevAlerts };
    },
    onError: (_err, _vars, ctx) => {
      ctx?.prevPulse.forEach(([key, data]) => qc.setQueryData(key, data));
      ctx?.prevAlerts.forEach(([key, data]) => qc.setQueryData(key, data));
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["pulse"] });
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["completed"] });
      qc.invalidateQueries({ queryKey: ["client"] });
      qc.invalidateQueries({ queryKey: ["digest"] });
    },
  });
}

export function useDraftEmail(source: DraftEmailSource | null) {
  return useQuery({
    queryKey: ["draft", source],
    queryFn: () => {
      if (!source) throw new Error("No draft source");
      if (source.type === "alert") {
        return api.post<DraftEmailResponse>("/api/monitor/draft-email", {
          alert_id: source.alertId,
        });
      }
      return api.post<DraftEmailResponse>("/api/monitor/draft-email", {
        client_id: source.clientId,
        context: source.context,
        talking_points: source.talkingPoints,
      });
    },
    enabled: !!source,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useClientDetail(clientId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.clientDetail(clientId ?? ""),
    queryFn: () =>
      api.get<ClientDetail>(`/api/monitor/clients/${encodeURIComponent(clientId!)}`),
    enabled: !!clientId,
  });
}

export function useDigest(simulatedDate: string, enabled = true) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: queryKeys.digest(simulatedDate),
    queryFn: () => {
      const params = new URLSearchParams({ simulated_date: simulatedDate });
      return api.get<DigestResponse>(`/api/monitor/digest?${params}`);
    },
    enabled: enabled && !!simulatedDate,
    staleTime: 60 * 60 * 1000,
  });

  const refreshDigest = useCallback(async () => {
    const params = new URLSearchParams({
      simulated_date: simulatedDate,
      refresh: "true",
    });
    const data = await api.get<DigestResponse>(`/api/monitor/digest?${params}`);
    qc.setQueryData(queryKeys.digest(simulatedDate), data);
    return data;
  }, [qc, simulatedDate]);

  return { ...query, refreshDigest };
}

export function useChat() {
  return useMutation<
    ChatResponse,
    ApiError,
    { query: string; clientId?: string }
  >({
    mutationFn: ({ query, clientId }) =>
      api.post<ChatResponse>("/api/chat", {
        query,
        ...(clientId ? { client_id: clientId } : {}),
      }),
  });
}

export function useBrief() {
  return useMutation<BriefResponse, ApiError, string>({
    mutationFn: (clientId: string) =>
      api.post<BriefResponse>("/api/chat/brief", { client_id: clientId }),
  });
}

export function useUpload() {
  const qc = useQueryClient();
  return useMutation<StoredDocument, ApiError, File>({
    mutationFn: uploadDocument,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useExportData() {
  return useMutation<void, ApiError, ExportType>({
    mutationFn: (type) => downloadExport(type),
  });
}

export function useClearData() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ ok: boolean }>("/api/settings/clear-data"),
    onSuccess: () => qc.invalidateQueries(),
  });
}
