"""
Supabase JWT verification (optional).

When SUPABASE_JWT_SECRET is configured, every API request must carry a valid
Supabase access token (`Authorization: Bearer <jwt>`); the decoded user is
attached to request.state.user for downstream handlers / future multi-tenancy.

When the secret is unset (local dev, CI, current deployments), this is a no-op
so the app keeps working exactly as before — consistent with the API-key
stopgap in app.security.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Header, HTTPException, Request, status

logger = logging.getLogger("jarvis.auth")


def _jwt_secret() -> Optional[str]:
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    return secret.strip() if secret else None


def supabase_auth_enabled() -> bool:
    return _jwt_secret() is not None


async def verify_supabase_jwt(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> None:
    """FastAPI dependency: validate the Supabase JWT when configured."""
    secret = _jwt_secret()
    if not secret:
        return  # Auth not configured — run open (see module docstring).

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    token = authorization.split(" ", 1)[1].strip()
    try:
        import jwt  # PyJWT, imported lazily so it is only needed when enabled.

        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except Exception:  # noqa: BLE001 - any decode/verify failure is a 401
        logger.warning("Rejected request with an invalid Supabase JWT")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    request.state.user = {"id": payload.get("sub"), "email": payload.get("email")}
