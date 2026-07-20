import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type {
  CreditHistoryResponse,
  CreditRequestResponse,
  CreditSummary,
} from "@/lib/credits";

export const creditQueryKeys = {
  summary: ["credits"] as const,
  history: (limit: number, offset: number) =>
    ["credits", "history", limit, offset] as const,
};

export function useCreditSummary() {
  return useQuery<CreditSummary, ApiError>({
    queryKey: creditQueryKeys.summary,
    queryFn: () => api.get<CreditSummary>("/api/credits"),
    staleTime: 15_000,
    refetchOnWindowFocus: true,
    retry: 1,
  });
}

export function useCreditHistory(limit: number, offset: number) {
  return useQuery<CreditHistoryResponse, ApiError>({
    queryKey: creditQueryKeys.history(limit, offset),
    queryFn: () =>
      api.get<CreditHistoryResponse>(
        `/api/credits/history?limit=${limit}&offset=${offset}`
      ),
    placeholderData: (previous) => previous,
  });
}

export function useRequestCredits() {
  const queryClient = useQueryClient();
  return useMutation<CreditRequestResponse, ApiError, string>({
    mutationFn: (message) =>
      api.post<CreditRequestResponse>("/api/credits/requests", { message }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["credits", "history"] }),
  });
}
