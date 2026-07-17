"""
In-memory TTL cache for LLM responses to reduce API calls and latency.

Tenant scoping: all product code uses the ``*_scoped`` helpers, which prefix
keys with the current org id (``{org_id}|{key}``) so cache entries can never be
shared across workspaces. The raw ``get``/``set_`` primitives remain for the
cache's own plumbing and tests. CI guards that routers/services only use the
scoped API (scripts/check_sql_fstrings.py also checks cache usage).

This cache is process-local, which is correct for the current single-instance
deployment; the Redis decision gate is documented in NEXT_PLAN/RFC (adopt only
when there is more than one API instance).
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Optional

from app.context import TenantContext, get_current_tenant

# Single in-memory store: key -> (value, expiry_ts)
_store: dict[str, tuple[Any, float]] = {}
_lock = threading.Lock()

# Default TTLs (seconds)
BRIEF_TTL = 3600  # 1 hour
DRAFT_EMAIL_TTL = 1800  # 30 min
CHAT_TTL = 300  # 5 min
STRUCTURED_CTX_TTL = 90  # 90 s – cache for Ask Jarvis structured context to avoid DB on every query
EXTRACT_TTL = 86400  # 24 h (ingestion extraction by content hash)
PULSE_TTL = 60  # 1 min – shared by /pulse and /digest to avoid duplicate DB work


def _now() -> float:
    return time.monotonic()


def get(key: str) -> Optional[Any]:
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if _now() >= expiry:
            del _store[key]
            return None
        return value


def set_(key: str, value: Any, ttl_seconds: int) -> None:
    with _lock:
        _store[key] = (value, _now() + ttl_seconds)


def delete(key: str) -> None:
    with _lock:
        _store.pop(key, None)


def delete_prefix(prefix: str) -> int:
    """Remove all keys starting with prefix. Returns count removed."""
    with _lock:
        to_del = [k for k in _store if k.startswith(prefix)]
        for k in to_del:
            del _store[k]
        return len(to_del)


def hash_query_for_key(query: str) -> str:
    """Stable hash for normalizing chat query for cache key."""
    normalized = (query or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Tenant-scoped API — the only API product code should use.
# ---------------------------------------------------------------------------


def _org_id(ctx: Optional[TenantContext]) -> str:
    tenant = ctx or get_current_tenant()
    if tenant is None or not tenant.org_id:
        raise RuntimeError(
            "Scoped cache access requires a tenant context; bind one via the "
            "request dependency or pass ctx explicitly from jobs."
        )
    return tenant.org_id


def scoped_key(key: str, ctx: Optional[TenantContext] = None) -> str:
    return f"{_org_id(ctx)}|{key}"


def get_scoped(key: str, ctx: Optional[TenantContext] = None) -> Optional[Any]:
    return get(scoped_key(key, ctx))


def set_scoped(key: str, value: Any, ttl_seconds: int, ctx: Optional[TenantContext] = None) -> None:
    set_(scoped_key(key, ctx), value, ttl_seconds)


def delete_scoped(key: str, ctx: Optional[TenantContext] = None) -> None:
    delete(scoped_key(key, ctx))


def delete_prefix_scoped(prefix: str, ctx: Optional[TenantContext] = None) -> int:
    return delete_prefix(scoped_key(prefix, ctx))


def invalidate_pulse_caches(ctx: Optional[TenantContext] = None) -> None:
    """Clear this org's pulse snapshots when alert or client data changes."""
    delete_prefix_scoped("pulse:", ctx)


def invalidate_client_ai_caches(client_id: str, ctx: Optional[TenantContext] = None) -> None:
    """Bust this org's LLM caches when client data or documents change."""
    from app.services.prompts import PROMPT_VERSION

    delete_scoped(f"brief:{PROMPT_VERSION}:{client_id}", ctx)
    delete_scoped(f"summary:{PROMPT_VERSION}:{client_id}", ctx)
    delete_scoped(f"review-note:{PROMPT_VERSION}:{client_id}", ctx)
    delete_prefix_scoped("chat:", ctx)
    delete_prefix_scoped("digest:", ctx)
    invalidate_pulse_caches(ctx)


def invalidate_all_ai_caches(ctx: Optional[TenantContext] = None) -> None:
    """Clear all AI-related cache prefixes for this org (full data reset)."""
    for prefix in ("brief:", "draft:", "chat:", "extract:", "digest:", "summary:", "review-note:", "pulse:"):
        delete_prefix_scoped(prefix, ctx)


def clear_all_unscoped_for_tests() -> None:
    """Wipe the entire store. Test helper only."""
    with _lock:
        _store.clear()
