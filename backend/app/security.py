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


def _rate_limit_key(request) -> str:
    """Per-tenant rate limiting: org/user when authenticated, else client IP.

    Router-level auth dependencies run before endpoint rate-limit decorators,
    so ``request.state.tenant`` is populated by the time this is called.
    """
    tenant = getattr(getattr(request, "state", None), "tenant", None)
    if tenant is not None:
        user_part = tenant.user_id or tenant.role
        return f"org:{tenant.org_id}:{user_part}"
    return get_remote_address(request)


# Global default applied per-endpoint (decorated routes); key is tenant-aware.
# RATE_LIMIT_ENABLED=false disables limiting (test suites only).
limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=["120/minute"],
    enabled=os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower() != "false",
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
