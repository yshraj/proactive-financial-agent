// React Query hooks wrapping the typed API client.
// Centralizes fetching, caching, dedup, retry and invalidation so pages
// don't hand-roll loading/error/data state.
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type {
  Alert,
  BriefResponse,
  ChatResponse,
  Client,
  PulseData,
  StoredDocument,
} from "@/lib/types";

export const queryKeys = {
  pulse: (date: string) => ["pulse", date] as const,
  completed: () => ["completed"] as const,
  clients: () => ["clients"] as const,
  alerts: (params: Record<string, string>) => ["alerts", params] as const,
  documents: () => ["documents"] as const,
};

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
  });
}

export function useDocuments() {
  return useQuery({
    queryKey: queryKeys.documents(),
    queryFn: () => api.get<StoredDocument[]>("/api/ingest/documents"),
  });
}

export function useUpdateAlertStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { alertId: string; status: string }) =>
      api.patch<Alert>(`/api/monitor/alerts/${encodeURIComponent(vars.alertId)}/status`, {
        status: vars.status,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pulse"] });
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["completed"] });
    },
  });
}

export function useDraftEmail(alertId: string | null) {
  return useQuery({
    queryKey: ["draft", alertId],
    queryFn: () =>
      api.post<{ draft: string }>("/api/monitor/draft-email", {
        alert_id: alertId,
      }),
    enabled: !!alertId,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useChat() {
  return useMutation<ChatResponse, ApiError, string>({
    mutationFn: (query: string) => api.post<ChatResponse>("/api/chat", { query }),
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
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.postForm<StoredDocument>("/api/ingest/upload", form);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useClearData() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ ok: boolean }>("/api/settings/clear-data"),
    onSuccess: () => qc.invalidateQueries(),
  });
}
