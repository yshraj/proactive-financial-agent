"""
Authentication mode, API-key verification, and rate limiting.

Auth posture is fail-closed by default:

- ``AUTH_MODE=required`` (the default): the app refuses to start unless
  Supabase JWT verification is configured (``SUPABASE_URL`` and/or
  ``SUPABASE_JWT_SECRET``). Browsers authenticate with a Supabase JWT only.
- ``AUTH_MODE=demo``: anonymous access is allowed (single shared demo
  workspace). Refused outright when ``ENV``/``ENVIRONMENT`` is production.

``API_KEY`` is an optional *service-to-service* credential (scripts, uptime
probes). It is never shipped to the browser; see app.auth.authenticate_request
for how the two schemes combine.
"""
from __future__ import annotations

import logging
import os
import secrets
from typing import Optional

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("jarvis.security")

AUTH_MODE_REQUIRED = "required"
AUTH_MODE_DEMO = "demo"


def session_id_from(request) -> Optional[str]:
    """The browser session id (X-Session-Id), used to scope demo-mode limits.

    Anonymous demo callers all share one tenant (org:default:demo), so without
    this every visitor would draw from one global bucket. The frontend mints a
    per-browser id; it is spoofable, so IP remains the fallback for callers that
    send none. Truncated to bound the key space.
    """
    raw = request.headers.get("X-Session-Id") if hasattr(request, "headers") else None
    return raw.strip()[:64] if raw and raw.strip() else None


def client_ip_from(request) -> str:
    """Best-effort real client IP, proxy-aware.

    Behind the reverse proxy (nginx/Caddy) the direct peer is the proxy, so the
    real client IP arrives in ``X-Forwarded-For`` (first hop) or ``X-Real-IP``.
    We honour those when present and fall back to the direct connection IP.

    Caveat: these headers are client-settable when the app is NOT behind a
    trusted proxy. That is acceptable here because the IP is used only for the
    cost-budget bucket (a spend guard), never for authentication. The production
    proxy must be configured to overwrite ``X-Forwarded-For`` so a client can't
    forge it.
    """
    headers = getattr(request, "headers", None)
    if headers is not None:
        xff = headers.get("X-Forwarded-For")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first
        xri = headers.get("X-Real-IP")
        if xri and xri.strip():
            return xri.strip()
    return get_remote_address(request)


def _rate_limit_key(request) -> str:
    """Per-minute / default rate-limit bucket: real user when authenticated,
    else per browser session (demo mode), else client IP.

    Session-scoped so honest concurrent demo users on one NAT'd IP don't starve
    each other minute-to-minute. The per-DAY cost budgets use daily_budget_key
    instead — see there for why session is deliberately excluded.

    Router-level auth dependencies run before endpoint rate-limit decorators,
    so ``request.state.tenant`` is populated by the time this is called.
    """
    tenant = getattr(getattr(request, "state", None), "tenant", None)
    if tenant is not None:
        # A real signed-in user keys on their own identity.
        if tenant.user_id:
            return f"org:{tenant.org_id}:{tenant.user_id}"
        # Shared/demo contexts: separate each browser session, IP as fallback.
        session = session_id_from(request)
        if session:
            return f"org:{tenant.org_id}:sess:{session}"
        return f"org:{tenant.org_id}:ip:{client_ip_from(request)}"
    session = session_id_from(request)
    if session:
        return f"sess:{session}"
    return client_ip_from(request)


def daily_budget_key(request) -> str:
    """Key for the per-day cost budgets (LLM / ingestion).

    Authenticated users key on their own identity. Anonymous/demo callers key on
    the client IP — deliberately NOT the client-supplied ``X-Session-Id``, which
    is trivially rotated to mint a fresh daily budget. Anchoring the daily spend
    to the IP means rotating only the session header no longer resets it.

    This RAISES THE BAR against casual header-rotation abuse; it is NOT
    equivalent to real per-user auth (a determined attacker can still change
    source IPs). Real auth remains explicitly out of scope for this pass.
    """
    tenant = getattr(getattr(request, "state", None), "tenant", None)
    if tenant is not None and tenant.user_id:
        return f"org:{tenant.org_id}:{tenant.user_id}"
    ip = client_ip_from(request)
    if tenant is not None:
        return f"org:{tenant.org_id}:ip:{ip}"
    return f"ip:{ip}"


# Global default applied per-endpoint (decorated routes); key is tenant-aware.
# RATE_LIMIT_ENABLED=false disables limiting (test suites only).
limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=["120/minute"],
    enabled=os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower() != "false",
    # Emit Retry-After / X-RateLimit-* so clients (and our 429 body's reset_at)
    # get an accurate window-reset time instead of guessing.
    headers_enabled=True,
)

# Daily cost budgets (per rate-limit key — i.e. per user, or per browser session
# in demo mode). These are SHARED buckets: every endpoint tagged with the same
# scope draws from one counter, so the LLM budget caps total generations across
# copilot + brief + digest + draft-email + review-note, not each in isolation.
# Tunable via env without a code change; defaults come from the hardening plan.
LLM_DAILY_LIMIT = os.environ.get("LLM_DAILY_LIMIT", "30/day").strip()
INGEST_DAILY_LIMIT = os.environ.get("INGEST_DAILY_LIMIT", "5/day").strip()

# scope strings double as the machine-readable limit_type in the 429 body / logs.
LLM_SCOPE = "llm"
INGEST_SCOPE = "ingestion"

# Daily budgets key on IP (not session) so header-rotation can't reset them.
llm_daily_limit = limiter.shared_limit(LLM_DAILY_LIMIT, scope=LLM_SCOPE, key_func=daily_budget_key)
ingestion_daily_limit = limiter.shared_limit(
    INGEST_DAILY_LIMIT, scope=INGEST_SCOPE, key_func=daily_budget_key
)


def limit_type_for(scope: Optional[str], path: str) -> str:
    """Classify a rate-limit hit for the client and for pricing analytics.

    Prefers the shared-budget scope (``llm``/``ingestion``) when that was the
    limit hit; otherwise infers from the path, defaulting to ``request`` for the
    per-minute/global limits.
    """
    if scope in (LLM_SCOPE, INGEST_SCOPE):
        return scope
    if path.startswith("/api/ingest"):
        return INGEST_SCOPE
    if path.startswith("/api/chat"):
        return LLM_SCOPE
    if path in _LLM_MONITOR_PATHS:
        return LLM_SCOPE
    return "request"


# Monitor endpoints that call the LLM (used only for classifying a per-minute hit).
_LLM_MONITOR_PATHS = frozenset(
    {"/api/monitor/digest", "/api/monitor/draft-email"}
)


def _expected_key() -> Optional[str]:
    key = os.environ.get("API_KEY")
    return key.strip() if key else None


def api_key_configured() -> bool:
    return bool(_expected_key())


def api_key_matches(candidate: Optional[str]) -> bool:
    """Constant-time comparison against the configured service API key."""
    expected = _expected_key()
    if not expected or not candidate:
        return False
    return secrets.compare_digest(candidate, expected)


# ---------------------------------------------------------------------------
# Shared access code — the "locked front door" for public demo deployments.
#
# This is NOT authentication. It is a single shared secret checked on every
# /api/* request (X-Access-Code header) so a public, demo-mode URL cannot be
# hit freely by anyone who finds it. Real per-user auth is Supabase JWT (see
# app.auth). When ACCESS_CODE is unset the gate is disabled (local dev / tests).
# ---------------------------------------------------------------------------


def _expected_access_code() -> Optional[str]:
    code = os.environ.get("ACCESS_CODE")
    return code.strip() if code else None


def access_code_configured() -> bool:
    return bool(_expected_access_code())


def access_code_matches(candidate: Optional[str]) -> bool:
    """Constant-time comparison against the configured shared access code."""
    expected = _expected_access_code()
    if not expected or not candidate:
        return False
    return secrets.compare_digest(candidate.strip(), expected)


def _supabase_configured() -> bool:
    url = os.environ.get("SUPABASE_URL", "").strip()
    secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
    return bool(url or secret)


def auth_configured() -> bool:
    """True when at least one auth mechanism is enabled."""
    return api_key_configured() or _supabase_configured()


def is_production() -> bool:
    env = os.environ.get("ENV", os.environ.get("ENVIRONMENT", "")).lower()
    return env in ("production", "prod")


def auth_mode() -> str:
    """Resolve AUTH_MODE. Unknown values fail closed to ``required``."""
    raw = (os.environ.get("AUTH_MODE") or AUTH_MODE_REQUIRED).strip().lower()
    if raw == AUTH_MODE_DEMO:
        return AUTH_MODE_DEMO
    if raw != AUTH_MODE_REQUIRED:
        logger.warning("Unknown AUTH_MODE=%r — treating as 'required' (fail closed).", raw)
    return AUTH_MODE_REQUIRED


def demo_mode_enabled() -> bool:
    return auth_mode() == AUTH_MODE_DEMO


def enforce_auth_mode() -> None:
    """Fail fast at startup when the auth configuration is unsafe.

    - demo mode is forbidden in production;
    - required mode (the default) refuses to boot without Supabase JWT config,
      in every environment.
    """
    mode = auth_mode()
    if mode == AUTH_MODE_DEMO:
        if is_production():
            raise RuntimeError(
                "AUTH_MODE=demo is not allowed when ENV/ENVIRONMENT is production. "
                "Configure Supabase auth (SUPABASE_URL) and set AUTH_MODE=required."
            )
        logger.warning(
            "AUTH_MODE=demo — the API accepts unauthenticated requests into a shared "
            "demo workspace. Never use this outside local development or previews."
        )
        return

    if not _supabase_configured():
        raise RuntimeError(
            "AUTH_MODE=required (the default) needs Supabase JWT auth configured: "
            "set SUPABASE_URL (asymmetric JWKS verification) and/or SUPABASE_JWT_SECRET "
            "(legacy HS256). For local development without auth, set AUTH_MODE=demo "
            "explicitly."
        )


def data_reset_enabled() -> bool:
    """Destructive data reset is opt-in via env, and never in production."""
    if is_production():
        return os.environ.get("ALLOW_DATA_RESET", "").lower() == "force"
    return os.environ.get("ALLOW_DATA_RESET", "").lower() in ("1", "true", "yes", "force")
