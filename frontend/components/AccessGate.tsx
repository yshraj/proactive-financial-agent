import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/router";
import { Loader2 } from "lucide-react";
import { AuthShell } from "./AuthShell";
import { Button } from "./ui";
import { api, ApiError } from "../lib/api";
import {
  getAccessCode,
  setAccessCode,
  clearAccessCode,
} from "../lib/accessCode";
import { BARE_ROUTES } from "../lib/routes";

// Once the backend confirms the door is open for this browser, remember it so
// route changes don't re-probe on every navigation.
let verifiedThisSession = false;

type GateStatus = "checking" | "locked" | "unlocked";

/** Probe the front-door gate. Resolves true when open (valid code or gate off). */
async function probeAccess(): Promise<boolean> {
  try {
    await api.get<{ ok: boolean }>("/api/access/check", { timeoutMs: 10_000 });
    return true;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return false;
    // Network/other errors: don't hard-lock the user out of a reachable app —
    // let the real request surface the error. Treat as "not gated here".
    return true;
  }
}

/**
 * Shared front-door gate. When the backend requires an access code and this
 * browser hasn't supplied a valid one, renders a code-entry screen instead of
 * the app. A no-op on bare (marketing/auth) routes, which make no API calls.
 */
export function AccessGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const isBare = BARE_ROUTES.has(router.pathname);
  const [status, setStatus] = useState<GateStatus>(
    verifiedThisSession ? "unlocked" : "checking"
  );
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isBare || verifiedThisSession) return;
    let active = true;
    (async () => {
      const open = await probeAccess();
      if (!active) return;
      if (open) {
        verifiedThisSession = true;
        setStatus("unlocked");
      } else {
        setStatus("locked");
      }
    })();
    return () => {
      active = false;
    };
  }, [isBare]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = code.trim();
      if (!trimmed) return;
      setSubmitting(true);
      setError("");
      setAccessCode(trimmed);
      const open = await probeAccess();
      if (open) {
        verifiedThisSession = true;
        setStatus("unlocked");
      } else {
        clearAccessCode();
        setError("That access code isn't right. Please try again.");
      }
      setSubmitting(false);
    },
    [code]
  );

  // Bare routes and the resolved-open state render the app directly.
  if (isBare || status === "unlocked") return <>{children}</>;

  if (status === "checking") {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-gray-50"
        role="status"
        aria-label="Loading"
      >
        <Loader2 className="h-6 w-6 animate-spin text-brand-600" aria-hidden />
      </div>
    );
  }

  return (
    <AuthShell
      title="Enter access code"
      subtitle="This is a private demo. Enter the shared access code to continue."
    >
      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        <div>
          <label
            htmlFor="access-code"
            className="mb-2 block text-sm font-medium text-slate-700"
          >
            Access code
          </label>
          <input
            id="access-code"
            type="password"
            autoComplete="off"
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Enter your code"
            className="input"
            data-testid="access-code-input"
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <Button
          type="submit"
          loading={submitting}
          disabled={!code.trim()}
          size="lg"
          className="mt-2 w-full"
          data-testid="access-code-submit"
        >
          Unlock demo
        </Button>
      </form>
    </AuthShell>
  );
}

export default AccessGate;
