"""
Tenant resolution and JIT workspace provisioning.

The verified JWT subject is mapped to (org_id, role) through
``provision_user_workspace()`` — a SECURITY DEFINER SQL function (see the RLS
migration) that atomically:

1. upserts the ``users`` row,
2. returns an existing membership when one exists,
3. otherwise lets the first-ever user claim the default workspace (which holds
   any pre-tenancy backfilled data), and gives every later user a personal
   workspace.

Resolutions are cached in-process for a short TTL so the membership lookup does
not hit Postgres on every request.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from app.context import ROLE_ADVISER, TenantContext
from app.db import get_cursor

logger = logging.getLogger("jarvis.tenancy")

_CACHE_TTL_SECONDS = 60.0
_cache: "dict[str, tuple[TenantContext, float]]" = {}
_lock = threading.Lock()


def _cached(user_id: str) -> Optional[TenantContext]:
    with _lock:
        hit = _cache.get(user_id)
        if hit is None:
            return None
        ctx, expires = hit
        if time.monotonic() >= expires:
            _cache.pop(user_id, None)
            return None
        return ctx


def _remember(user_id: str, ctx: TenantContext) -> None:
    with _lock:
        _cache[user_id] = (ctx, time.monotonic() + _CACHE_TTL_SECONDS)


def invalidate_cache(user_id: Optional[str] = None) -> None:
    with _lock:
        if user_id is None:
            _cache.clear()
        else:
            _cache.pop(user_id, None)


def resolve_tenant(
    *, user_id: str, email: Optional[str], request_id: Optional[str] = None
) -> TenantContext:
    """Resolve (and JIT-provision) the workspace for an authenticated user."""
    cached = _cached(user_id)
    if cached is not None:
        if cached.request_id == request_id:
            return cached
        return TenantContext(
            org_id=cached.org_id,
            user_id=cached.user_id,
            role=cached.role,
            email=cached.email,
            request_id=request_id,
        )

    # Bootstrap context: only app.user_id is bound, which is what the
    # users/org_memberships bootstrap RLS policies key on.
    bootstrap = TenantContext(org_id="", user_id=user_id, role=ROLE_ADVISER)
    with get_cursor(commit=True, ctx=bootstrap) as cur:
        cur.execute(
            "SELECT out_org_id, out_role FROM provision_user_workspace(%s::uuid, %s)",
            (user_id, email or ""),
        )
        row = cur.fetchone()
    if not row or not row.get("out_org_id"):
        raise RuntimeError(f"Workspace provisioning returned no membership for user {user_id}")

    ctx = TenantContext(
        org_id=str(row["out_org_id"]),
        user_id=user_id,
        role=str(row.get("out_role") or ROLE_ADVISER),
        email=email,
        request_id=request_id,
    )
    _remember(user_id, ctx)
    logger.info(
        "tenant resolved: user=%s org=%s role=%s", user_id, ctx.org_id, ctx.role
    )
    return ctx
