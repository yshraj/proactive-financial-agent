// Centralized, typed API client.
// - Single source for the base URL.
// - Consistent timeout + error shape so callers can render recoverable error UI.
// - Browser auth is the Supabase JWT only. The old NEXT_PUBLIC_API_KEY path was
//   removed: anything shipped in the JS bundle is public, so a browser-side API
//   key provides no security. API_KEY remains a server-to-server credential.

import { getSupabaseClient, isSupabaseConfigured } from "./supabase/client";
import { getAccessCode, getSessionId } from "./accessCode";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const DEFAULT_TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Extract a user-facing message from an unknown caught error. */
export function errorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return fallback;
}

async function authHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  if (isSupabaseConfigured) {
    try {
      const token = await getAccessToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    } catch {
      // Proceed unauthenticated; the backend will reject if it requires a token.
    }
  }
  // Shared front-door code + per-session id for demo-mode rate limiting.
  const code = getAccessCode();
  if (code) headers["X-Access-Code"] = code;
  const sessionId = getSessionId();
  if (sessionId) headers["X-Session-Id"] = sessionId;
  return headers;
}

let cachedToken: string | null = null;
let tokenExpiresAt = 0;
let authListenerReady = false;

/** Cache the Supabase access token to avoid getSession() on every parallel API call. */
async function getAccessToken(): Promise<string | null> {
  const supabase = await getSupabaseClient();
  if (!supabase) return null;

  if (!authListenerReady) {
    authListenerReady = true;
    supabase.auth.onAuthStateChange((_event, session) => {
      cachedToken = session?.access_token ?? null;
      tokenExpiresAt = session?.expires_at ? session.expires_at * 1000 : 0;
    });
  }

  const now = Date.now();
  if (cachedToken && tokenExpiresAt > now + 30_000) {
    return cachedToken;
  }

  const session = (await supabase.auth.getSession()).data.session;
  cachedToken = session?.access_token ?? null;
  tokenExpiresAt = session?.expires_at ? session.expires_at * 1000 : 0;
  return cachedToken;
}

function extractDetailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.message === "string") return obj.message;
    if (Array.isArray(detail)) {
      return (detail as Array<{ msg?: string }>)
        .map((d) => d?.msg)
        .filter(Boolean)
        .join(", ");
    }
  }
  return fallback;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  timeoutMs?: number;
  isForm?: boolean;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { body, timeoutMs = DEFAULT_TIMEOUT_MS, isForm, headers, ...rest } =
    options;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: {
        ...(isForm ? {} : { "Content-Type": "application/json" }),
        ...(await authHeaders()),
        ...(headers as Record<string, string>),
      },
      body: isForm ? (body as BodyInit) : body ? JSON.stringify(body) : undefined,
    });

    let payload: unknown = null;
    const text = await res.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = text;
      }
    }

    if (!res.ok) {
      const detail =
        payload && typeof payload === "object" && "detail" in (payload as object)
          ? (payload as { detail: unknown }).detail
          : payload;
      const message = extractDetailMessage(
        detail,
        res.status === 404
          ? "Not found. Is the backend running?"
          : res.status >= 500 && process.env.NODE_ENV === "production"
            ? "Something went wrong on the server. Please try again."
            : `Request failed (${res.status})`
      );
      throw new ApiError(message, res.status, detail);
    }

    return payload as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("The request timed out. Please try again.", 0);
    }
    throw new ApiError(
      "Network error. Please check your connection and that the backend is running.",
      0
    );
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  get: <T>(path: string, opts?: RequestOptions) =>
    apiRequest<T>(path, { ...opts, method: "GET" }),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiRequest<T>(path, { ...opts, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    apiRequest<T>(path, { ...opts, method: "PATCH", body }),
  postForm: <T>(path: string, form: FormData, opts?: RequestOptions) =>
    apiRequest<T>(path, { ...opts, method: "POST", body: form, isForm: true }),
};
