"""
Request authentication -> tenant resolution.

Every /api/* route depends on :func:`authenticate_request`, which accepts one of:

1. ``Authorization: Bearer <supabase jwt>`` — browser traffic. Verified against
   the project JWKS (ES256/RS256) or the legacy HS256 secret, then resolved to
   a workspace via app.tenancy (JIT-provisioned on first login).
2. ``X-API-Key`` — optional service-to-service credential (scripts, probes).
   Acts on the service workspace. Never shipped to the browser.
3. Nothing — allowed only when ``AUTH_MODE=demo`` (shared demo workspace,
   refused in production at startup).

The resolved :class:`~app.context.TenantContext` is attached to
``request.state.tenant`` and bound to the context variables that db.get_cursor
and the cache/audit layers read.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Optional

from fastapi import Header, HTTPException, Request, status

from app import security
from app.context import (
    DEFAULT_ORG_ID,
    ROLE_DEMO,
    ROLE_SERVICE,
    TenantContext,
    set_current_tenant,
)

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


def verify_jwt_token(token: str) -> dict[str, Any]:
    """Verify a Supabase access token and return its payload. Raises 401."""
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
        ) from None

    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has no subject.",
        )
    return payload


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip() or None
    return None


def service_org_id() -> str:
    """Workspace that service (API-key) callers act on."""
    return (os.environ.get("SERVICE_ORG_ID") or DEFAULT_ORG_ID).strip()


async def authenticate_request(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
) -> TenantContext:
    """FastAPI dependency: authenticate the request and bind its tenant."""
    from app import tenancy  # local import to avoid a cycle via db

    request_id = getattr(getattr(request, "state", None), "request_id", None)
    token = _bearer_token(authorization)

    ctx: Optional[TenantContext] = None
    if token and supabase_auth_enabled():
        payload = verify_jwt_token(token)
        user = {"id": payload.get("sub"), "email": payload.get("email")}
        request.state.user = user
        ctx = tenancy.resolve_tenant(
            user_id=str(payload["sub"]),
            email=payload.get("email"),
            request_id=request_id,
        )
    elif x_api_key is not None and security.api_key_configured():
        if not security.api_key_matches(x_api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid API key.",
            )
        ctx = TenantContext(
            org_id=service_org_id(), role=ROLE_SERVICE, request_id=request_id
        )
    elif security.demo_mode_enabled():
        ctx = TenantContext(org_id=DEFAULT_ORG_ID, role=ROLE_DEMO, request_id=request_id)

    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Send a Supabase bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.tenant = ctx
    set_current_tenant(ctx)
    return ctx
