"""
In-memory TTL cache for LLM responses to reduce API calls and latency.
Used for: pre-meeting briefs (by client_id), draft emails (by alert_id), optional chat (by query hash).
"""
import hashlib
import threading
import time
from typing import Any, Optional

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


def invalidate_pulse_caches() -> None:
    """Clear pulse snapshots when alert or client data changes."""
    delete_prefix("pulse:")


def invalidate_client_ai_caches(client_id: str) -> None:
    """Bust LLM caches when client data or documents change."""
    from app.services.prompts import PROMPT_VERSION

    delete(f"brief:{PROMPT_VERSION}:{client_id}")
    delete(f"summary:{PROMPT_VERSION}:{client_id}")
    delete_prefix("chat:")
    delete_prefix("digest:")
    invalidate_pulse_caches()


def invalidate_all_ai_caches() -> None:
    """Clear all AI-related cache prefixes (used on full data reset)."""
    for prefix in ("brief:", "draft:", "chat:", "extract:", "digest:", "summary:", "pulse:"):
        delete_prefix(prefix)
