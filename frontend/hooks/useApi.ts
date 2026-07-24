// React Query hooks wrapping the typed API client.
// Centralizes fetching, caching, dedup, retry and invalidation so pages
// don't hand-roll loading/error/data state.
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback } from "react";
import {
  isAgentUnsupported,
  runCopilotWithProgress,
  type AgentStep,
  type CopilotRunResult,
} from "@/lib/agent";
import { api, ApiError } from "@/lib/api";
import { downloadExport, type ExportType } from "@/lib/export";
import { ingestTranscript } from "@/lib/ingest";
import type {
  Alert,
  BookAnalytics,
  BriefResponse,
  ChatResponse,
  Client,
  ClientDetail,
  ClientUpdateInput,
  ComplianceScanResponse,
  CompliancePosture,
  AuditLogResponse,
  DigestResponse,
  DraftEmailResponse,
  DraftEmailSource,
  NoteTemplate,
  Playbook,
  PulseData,
  RenderedTemplate,
  ReviewNoteResponse,
  StoredDocument,
  UploadLimits,
} from "@/lib/types";

// List pagination: default page, and the server-enforced ceiling. Dropdowns
// that need the whole book request FULL_BOOK (still bounded at 200).
export const LIST_PAGE_SIZE = 50;
export const MAX_LIST_PAGE = 200;

export const queryKeys = {
  pulse: (date: string) => ["pulse", date] as const,
  digest: (date: string) => ["digest", date] as const,
  completed: () => ["completed"] as const,
  clients: (limit: number = LIST_PAGE_SIZE) => ["clients", limit] as const,
  analytics: () => ["analytics"] as const,
  clientDetail: (id: string) => ["client", id] as const,
  alerts: (params: Record<string, string>) => ["alerts", params] as const,
  documents: () => ["documents"] as const,
};

/** Paginated client list response (total drives page controls). */
export type ClientsPage = { clients: Client[]; total: number };
export type AlertsPage = { alerts: Alert[]; total: number };

/** Prefetch client list on nav hover to warm cache before navigation. */
export function prefetchClients(qc: ReturnType<typeof useQueryClient>) {
  return qc.prefetchQuery({
    queryKey: queryKeys.clients(),
    queryFn: () =>
      api.get<ClientsPage>(`/api/monitor/clients?limit=${LIST_PAGE_SIZE}`),
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

/**
 * Client list. Pass a limit to grow the page ("Load more"); dropdowns that need
 * the whole book pass MAX_LIST_PAGE. The server clamps the limit to 200.
 */
export function useClients(limit: number = LIST_PAGE_SIZE) {
  return useQuery({
    queryKey: queryKeys.clients(limit),
    queryFn: () =>
      api.get<ClientsPage>(`/api/monitor/clients?limit=${limit}`),
    staleTime: 60_000,
    gcTime: 10 * 60_000,
  });
}

export function useBookAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics(),
    queryFn: () => api.get<BookAnalytics>("/api/monitor/analytics"),
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
  limit?: number;
}) {
  const search = new URLSearchParams({
    simulated_date: params.simulated_date,
    days: String(params.days),
    limit: String(params.limit ?? LIST_PAGE_SIZE),
  });
  if (params.type && params.type !== "All") search.set("type", params.type);
  if (params.priority && params.priority !== "All")
    search.set("priority", params.priority);
  if (params.status && params.status !== "All")
    search.set("status", params.status);
  const key = Object.fromEntries(search.entries());
  return useQuery({
    queryKey: queryKeys.alerts(key),
    queryFn: () => api.get<AlertsPage>(`/api/monitor/alerts?${search}`),
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

export function useUploadLimits() {
  return useQuery({
    queryKey: ["upload-limits"],
    queryFn: () => api.get<UploadLimits>("/api/ingest/limits"),
    // Deployment constants: fetch once per session.
    staleTime: Infinity,
    gcTime: Infinity,
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

      qc.setQueriesData<AlertsPage>({ queryKey: ["alerts"] }, (old) =>
        old
          ? {
              ...old,
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

export function useDraftEmail(source: DraftEmailSource | null, enabled = true) {
  const qc = useQueryClient();
  const fetchDraft = useCallback(
    (refresh = false) => {
      if (!source) throw new Error("No draft source");
      if (source.type === "alert") {
        return api.post<DraftEmailResponse>("/api/monitor/draft-email", {
          alert_id: source.alertId,
          ...(refresh ? { refresh: true } : {}),
        });
      }
      return api.post<DraftEmailResponse>("/api/monitor/draft-email", {
        client_id: source.clientId,
        context: source.context,
        talking_points: source.talkingPoints,
        ...(refresh ? { refresh: true } : {}),
      });
    },
    [source]
  );
  const query = useQuery({
    queryKey: ["draft", source],
    queryFn: () => fetchDraft(false),
    enabled: enabled && !!source,
    staleTime: 5 * 60 * 1000,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const regenerate = useCallback(async () => {
    const data = await fetchDraft(true);
    qc.setQueryData(["draft", source], data);
    return data;
  }, [fetchDraft, qc, source]);
  return { ...query, regenerate };
}

export function useClientDetail(clientId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.clientDetail(clientId ?? ""),
    queryFn: () =>
      api.get<ClientDetail>(`/api/monitor/clients/${encodeURIComponent(clientId!)}`),
    enabled: !!clientId,
  });
}

export function useUpdateClient(clientId: string | undefined) {
  const qc = useQueryClient();
  return useMutation<Client, ApiError, ClientUpdateInput>({
    mutationFn: (input) =>
      api.patch<Client>(
        `/api/monitor/clients/${encodeURIComponent(clientId!)}`,
        input
      ),
    // Editing profile facts can change the AI summary, list rows and pulse, so
    // invalidate the dependent queries to refetch fresh data.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.clientDetail(clientId ?? "") });
      qc.invalidateQueries({ queryKey: ["clients"] });
      qc.invalidateQueries({ queryKey: ["pulse"] });
      qc.invalidateQueries({ queryKey: ["digest"] });
    },
  });
}

export function usePlaybooks() {
  return useQuery({
    queryKey: ["playbooks"],
    queryFn: () => api.get<{ playbooks: Playbook[] }>("/api/monitor/playbooks"),
    staleTime: 5 * 60_000,
  });
}

export function useApplyPlaybook(clientId: string | undefined) {
  const qc = useQueryClient();
  return useMutation<{ applied: number }, ApiError, string>({
    mutationFn: (playbookId) =>
      api.post<{ applied: number }>(
        `/api/monitor/clients/${encodeURIComponent(clientId!)}/apply-playbook`,
        { playbook_id: playbookId }
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.clientDetail(clientId ?? "") });
      qc.invalidateQueries({ queryKey: ["pulse"] });
      qc.invalidateQueries({ queryKey: ["clients"] });
    },
  });
}

export function useClientReviewNote(clientId: string | undefined) {
  const qc = useQueryClient();
  return useMutation<ReviewNoteResponse, ApiError, void>({
    mutationFn: () =>
      api.post<ReviewNoteResponse>(
        `/api/monitor/clients/${encodeURIComponent(clientId!)}/review-note`
      ),
    onSettled: () => qc.invalidateQueries({ queryKey: ["credits"] }),
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
    try {
      const data = await api.get<DigestResponse>(`/api/monitor/digest?${params}`);
      qc.setQueryData(queryKeys.digest(simulatedDate), data);
      return data;
    } finally {
      qc.invalidateQueries({ queryKey: ["credits"] });
    }
  }, [qc, simulatedDate]);

  return { ...query, refreshDigest };
}

export function useChat() {
  const qc = useQueryClient();
  return useMutation<
    ChatResponse,
    ApiError,
    { query: string; clientId?: string; conversationId?: string }
  >({
    mutationFn: ({ query, clientId, conversationId }) =>
      api.post<ChatResponse>("/api/chat", {
        query,
        ...(clientId ? { client_id: clientId } : {}),
        ...(conversationId ? { conversation_id: conversationId } : {}),
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["credits"] }),
  });
}

/**
 * Agentic copilot: create a durable agent run and poll its real step
 * timeline (streamed to `onSteps`) until the reviewed answer is ready.
 * Falls back to the synchronous /api/chat endpoint when the backend has no
 * agent runtime (older deployments), so the page degrades gracefully.
 */
export function useAgentChat() {
  const qc = useQueryClient();
  return useMutation<
    CopilotRunResult,
    ApiError,
    {
      query: string;
      clientId?: string;
      conversationId?: string;
      onSteps?: (steps: AgentStep[]) => void;
    }
  >({
    mutationFn: async ({ query, clientId, conversationId, onSteps }) => {
      try {
        return await runCopilotWithProgress({ query, clientId, conversationId, onSteps });
      } catch (error) {
        if (!isAgentUnsupported(error)) throw error;
        const legacy = await api.post<ChatResponse>("/api/chat", {
          query,
          ...(clientId ? { client_id: clientId } : {}),
          ...(conversationId ? { conversation_id: conversationId } : {}),
        });
        return {
          runId: "",
          conversationId: legacy.conversation_id ?? undefined,
          answer: legacy.answer,
          sources: legacy.sources ?? [],
        };
      }
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["credits"] }),
  });
}

export function useBrief() {
  const qc = useQueryClient();
  return useMutation<BriefResponse, ApiError, { clientId: string; refresh?: boolean }>({
    mutationFn: ({ clientId, refresh = false }) =>
      api.post<BriefResponse>("/api/chat/brief", {
        client_id: clientId,
        ...(refresh ? { refresh: true } : {}),
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["credits"] }),
  });
}

export function useNoteTemplates() {
  return useQuery({
    queryKey: ["note-templates"],
    queryFn: () => api.get<{ templates: NoteTemplate[] }>("/api/ingest/note-templates"),
    staleTime: 5 * 60_000,
  });
}

export function useNoteTemplate(templateId: string) {
  return useQuery({
    queryKey: ["note-template", templateId],
    queryFn: () =>
      api.get<RenderedTemplate>(
        `/api/ingest/note-templates/${encodeURIComponent(templateId)}`
      ),
    enabled: !!templateId,
    staleTime: 5 * 60_000,
  });
}

export function useIngestTranscript() {
  const qc = useQueryClient();
  return useMutation<StoredDocument, ApiError, { text: string; title?: string }>({
    mutationFn: ({ text, title }) => ingestTranscript(text, title),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["clients"] });
      qc.invalidateQueries({ queryKey: ["pulse"] });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["credits"] }),
  });
}

export function useAuditLog() {
  return useQuery({
    queryKey: ["audit"],
    queryFn: () => api.get<AuditLogResponse>("/api/compliance/audit?limit=50"),
    staleTime: 30_000,
  });
}

export function useCompliancePosture() {
  return useQuery({
    queryKey: ["posture"],
    queryFn: () => api.get<CompliancePosture>("/api/compliance/posture"),
    staleTime: 5 * 60_000,
  });
}

export function useApproveAuditEntry() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, number>({
    mutationFn: (entryId) =>
      api.post(`/api/compliance/audit/${entryId}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["audit"] }),
  });
}

export function useComplianceScan() {
  return useMutation<ComplianceScanResponse, ApiError, string>({
    mutationFn: (text: string) =>
      api.post<ComplianceScanResponse>("/api/compliance/scan", { text }),
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

interface LoadSampleDataResult {
  loaded: boolean;
  message: string;
  clients: number;
  alerts: number;
}

export function useLoadSampleData() {
  const qc = useQueryClient();
  return useMutation<LoadSampleDataResult, ApiError, void>({
    mutationFn: () =>
      api.post<LoadSampleDataResult>("/api/settings/load-sample-data"),
    onSuccess: () => qc.invalidateQueries(),
  });
}
