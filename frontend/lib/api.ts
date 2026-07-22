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

/** Structured envelope every backend error response carries. */
export interface ApiErrorEnvelope {
  code: string;
  message: string;
  retryable: boolean;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  /** Machine-readable code from the backend envelope (e.g. "rate_limited"). */
  code?: string;
  /** Whether the backend considers retrying worthwhile. */
  retryable?: boolean;
  /** Seconds until a rate limit resets (from the Retry-After header). */
  retryAfterSeconds?: number;
  /** Full parsed response body (envelope + handler extras like credit counts). */
  body?: unknown;
  constructor(
    message: string,
    status: number,
    detail?: unknown,
    extras?: {
      code?: string;
      retryable?: boolean;
      retryAfterSeconds?: number;
      body?: unknown;
    }
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = extras?.code;
    this.retryable = extras?.retryable;
    this.retryAfterSeconds = extras?.retryAfterSeconds;
    this.body = extras?.body;
  }
}

export const OFFLINE_MESSAGE = "You're offline. Please check your internet connection.";

// ---------------------------------------------------------------------------
// Cold-start signal. The first request after the app loads can take several
// seconds while the serverless backend spins up; subscribers (SystemBanners)
// show "Starting the service…" instead of appearing frozen. Once any response
// has arrived the service is warm and the signal never fires again.
// ---------------------------------------------------------------------------
const SLOW_START_NOTICE_MS = 2_500;
type SlowStartListener = (state: "slow" | "settled") => void;
const slowStartListeners = new Set<SlowStartListener>();
let backendResponded = false;
let slowStartAnnounced = false;

export function onSlowStart(listener: SlowStartListener): () => void {
  slowStartListeners.add(listener);
  return () => slowStartListeners.delete(listener);
}

function emitSlowStart(state: "slow" | "settled") {
  slowStartListeners.forEach((listener) => listener(state));
}

function trackColdStart(): () => void {
  if (backendResponded || typeof window === "undefined") return () => {};
  const timer = setTimeout(() => {
    if (!backendResponded && !slowStartAnnounced) {
      slowStartAnnounced = true;
      emitSlowStart("slow");
    }
  }, SLOW_START_NOTICE_MS);
  return () => {
    clearTimeout(timer);
    if (!backendResponded) {
      backendResponded = true;
      if (slowStartAnnounced) emitSlowStart("settled");
    }
  };
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

function parseEnvelope(payload: unknown): ApiErrorEnvelope | null {
  if (!payload || typeof payload !== "object") return null;
  const raw = (payload as { error?: unknown }).error;
  if (!raw || typeof raw !== "object") return null;
  const env = raw as Partial<ApiErrorEnvelope>;
  if (typeof env.code !== "string" || typeof env.message !== "string") return null;
  return { code: env.code, message: env.message, retryable: env.retryable === true };
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { body, timeoutMs = DEFAULT_TIMEOUT_MS, isForm, headers, ...rest } =
    options;

  // Fail fast when the browser knows it is offline: an immediate, honest
  // message beats a 60s timeout. Queries refetch automatically on reconnect.
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    throw new ApiError(OFFLINE_MESSAGE, 0, undefined, {
      code: "offline",
      retryable: true,
    });
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const settleColdStart = trackColdStart();

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
    settleColdStart();

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
      const envelope = parseEnvelope(payload);
      const detail =
        payload && typeof payload === "object" && "detail" in (payload as object)
          ? (payload as { detail: unknown }).detail
          : payload;
      const message = extractDetailMessage(
        detail,
        envelope?.message ??
          (res.status === 404
            ? "Not found. Is the backend running?"
            : res.status >= 500 && process.env.NODE_ENV === "production"
              ? "Something went wrong on the server. Please try again."
              : `Request failed (${res.status})`)
      );
      const retryAfterRaw = res.headers.get("Retry-After");
      const retryAfterSeconds =
        retryAfterRaw && /^\d+$/.test(retryAfterRaw)
          ? parseInt(retryAfterRaw, 10)
          : undefined;
      throw new ApiError(message, res.status, detail, {
        code: envelope?.code,
        retryable: envelope?.retryable,
        retryAfterSeconds,
        body: payload,
      });
    }

    return payload as T;
  } catch (err) {
    settleColdStart();
    if (err instanceof ApiError) throw err;
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("The request timed out. Please try again.", 0, undefined, {
        code: "timeout",
        retryable: true,
      });
    }
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      throw new ApiError(OFFLINE_MESSAGE, 0, undefined, {
        code: "offline",
        retryable: true,
      });
    }
    throw new ApiError(
      "Network error. Please check your connection and that the backend is running.",
      0,
      undefined,
      { code: "network", retryable: true }
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
