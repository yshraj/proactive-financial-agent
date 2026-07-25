import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type { ContactPayload, ContactResponse } from "@/lib/contact";

export function useSubmitContact() {
  return useMutation<ContactResponse, ApiError, ContactPayload>({
    mutationFn: (payload) => api.post<ContactResponse>("/api/contact", payload),
  });
}
