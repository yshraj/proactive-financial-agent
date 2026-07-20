// Shared front-door access code + per-browser session id.
//
// The access code is the "locked door" for the public demo: stored after the
// user enters it on the gate screen, then sent as X-Access-Code on every API
// request. The session id is a stable per-browser identifier sent as
// X-Session-Id so the backend can scope demo-mode rate limits per session
// rather than lumping every anonymous visitor into one global bucket.

const CODE_KEY = "kritifin.accessCode";
const SESSION_KEY = "kritifin.sessionId";

/** True in the browser; guards against SSR access to localStorage. */
const hasWindow = (): boolean => typeof window !== "undefined";

export function getAccessCode(): string | null {
  if (!hasWindow()) return null;
  try {
    return window.localStorage.getItem(CODE_KEY);
  } catch {
    return null;
  }
}

export function setAccessCode(code: string): void {
  if (!hasWindow()) return;
  try {
    window.localStorage.setItem(CODE_KEY, code);
  } catch {
    /* storage unavailable (private mode); the code just isn't remembered */
  }
}

export function clearAccessCode(): void {
  if (!hasWindow()) return;
  try {
    window.localStorage.removeItem(CODE_KEY);
  } catch {
    /* ignore */
  }
}

/** A stable per-browser id, minted lazily and persisted. */
export function getSessionId(): string | null {
  if (!hasWindow()) return null;
  try {
    let id = window.localStorage.getItem(SESSION_KEY);
    if (!id) {
      id =
        typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `s_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
      window.localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    return null;
  }
}
