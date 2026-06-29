"""
M0 stopgap security layer.

Until full authentication + multi-tenancy lands (see IMPLEMENTATION_PLAN.md M1),
this gates the API behind a shared API key and provides a reusable rate limiter,
so the public demo is not an open door to data exfiltration / cost abuse.

- If API_KEY is set, every request must send `X-API-Key: <key>`.
- If API_KEY is unset (e.g. local dev), the gate is open but a warning is logged.
"""
from __future__ import annotations

import logging
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("jarvis.security")

# Per-client-IP rate limiter. Global default applied unless overridden per-endpoint.
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


def _expected_key() -> Optional[str]:
    key = os.environ.get("API_KEY")
    return key.strip() if key else None


def auth_configured() -> bool:
    """True when at least one auth mechanism is enabled."""
    return bool(_expected_key()) or _supabase_configured()


def _supabase_configured() -> bool:
    url = os.environ.get("SUPABASE_URL", "").strip()
    secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
    return bool(url or secret)


def require_auth_in_production() -> None:
    """Fail fast at startup when production runs without auth configured."""
    env = os.environ.get("ENV", os.environ.get("ENVIRONMENT", "")).lower()
    if env not in ("production", "prod"):
        return
    if auth_configured():
        return
    raise RuntimeError(
        "Production requires API_KEY and/or Supabase JWT auth (SUPABASE_URL + SUPABASE_JWT_SECRET). "
        "Set ENV=development for local open mode."
    )


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """FastAPI dependency: enforce the shared API key when configured."""
    expected = _expected_key()
    if not expected:
        # Open in local/dev when no key is configured; warn once per process.
        if not getattr(require_api_key, "_warned", False):
            logger.warning(
                "API_KEY is not set — the API is UNAUTHENTICATED. Set API_KEY in production."
            )
            require_api_key._warned = True  # type: ignore[attr-defined]
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
        )


def data_reset_enabled() -> bool:
    """Destructive data reset is opt-in via env to avoid accidental wipes."""
    return os.environ.get("ALLOW_DATA_RESET", "").lower() in ("1", "true", "yes")
