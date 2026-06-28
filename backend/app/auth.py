"""
Supabase JWT verification (optional).

When Supabase auth is configured, every API request must carry a valid Supabase
access token (`Authorization: Bearer <jwt>`); the decoded user is attached to
request.state.user for downstream handlers / future multi-tenancy.

Supabase projects sign user access tokens with either:
  * asymmetric keys (ES256/RS256) exposed via JWKS  — the current default, or
  * the legacy symmetric secret (HS256).
Both are supported here. Verification is pinned to the project's issuer/audience.

When neither SUPABASE_URL nor SUPABASE_JWT_SECRET is set this is a no-op, so the
app keeps working as before in local dev / CI — consistent with the API-key
stopgap in app.security.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Optional

from fastapi import Header, HTTPException, Request, status

logger = logging.getLogger("jarvis.auth")

_AUDIENCE = "authenticated"
_LEEWAY = 10  # seconds of clock-skew tolerance


def _jwt_secret() -> Optional[str]:
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    return secret.strip() if secret else None


def _supabase_url() -> Optional[str]:
    url = os.environ.get("SUPABASE_URL")
    return url.strip().rstrip("/") if url else None


def supabase_auth_enabled() -> bool:
    return bool(_supabase_url() or _jwt_secret())


@lru_cache(maxsize=2)
def _jwk_client(jwks_url: str):
    import jwt  # PyJWT

    return jwt.PyJWKClient(jwks_url)


async def verify_supabase_jwt(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> None:
    """FastAPI dependency: validate the Supabase JWT when configured."""
    if not supabase_auth_enabled():
        return  # Auth not configured — run open (see module docstring).

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    token = authorization.split(" ", 1)[1].strip()
    url = _supabase_url()
    secret = _jwt_secret()

    import jwt  # PyJWT, imported lazily so it is only needed when enabled.

    common: dict[str, Any] = {"audience": _AUDIENCE, "leeway": _LEEWAY}
    if url:
        common["issuer"] = f"{url}/auth/v1"

    try:
        alg = jwt.get_unverified_header(token).get("alg", "")

        if alg.startswith(("ES", "RS", "PS")):
            if not url:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Asymmetric token but SUPABASE_URL is not configured.",
                )
            signing_key = _jwk_client(
                f"{url}/auth/v1/.well-known/jwks.json"
            ).get_signing_key_from_jwt(token)
            payload = jwt.decode(token, signing_key.key, algorithms=[alg], **common)
        elif alg == "HS256":
            if not secret:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="HS256 token but SUPABASE_JWT_SECRET is not configured.",
                )
            payload = jwt.decode(token, secret, algorithms=["HS256"], **common)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unsupported token algorithm.",
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - any decode/verify failure is a 401
        logger.warning("Rejected Supabase JWT: %s: %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    request.state.user = {"id": payload.get("sub"), "email": payload.get("email")}
