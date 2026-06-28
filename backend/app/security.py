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

from fastapi import Header, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("jarvis.security")

# Per-client-IP rate limiter. Applied to expensive (LLM) endpoints in the routers.
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def _expected_key() -> str | None:
    key = os.environ.get("API_KEY")
    return key.strip() if key else None


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
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
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
        )


def data_reset_enabled() -> bool:
    """Destructive data reset is opt-in via env to avoid accidental wipes."""
    return os.environ.get("ALLOW_DATA_RESET", "").lower() in ("1", "true", "yes")
