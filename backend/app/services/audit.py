"""
In-memory audit log of AI-generated outputs.

Records what AI produced (kind, client, model, a short preview) so advisers have
an accountability trail — a UK compliance expectation. Kept in-process like the
response cache (services/cache.py); it is not durable across restarts, which is
acceptable for the current single-instance deployment and documented as such.
Pure and thread-safe, so it is fully unit-testable.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any, Optional

# Bounded ring buffer so memory can't grow without limit.
_MAX_ENTRIES = 500
_entries: "deque[dict[str, Any]]" = deque(maxlen=_MAX_ENTRIES)
_lock = threading.Lock()
_counter = 0

# Preview length for the recorded output (avoid storing full client content).
_PREVIEW_CHARS = 160


def record(
    *,
    kind: str,
    timestamp: str,
    client_id: Optional[str] = None,
    client_name: Optional[str] = None,
    model: Optional[str] = None,
    output: Optional[str] = None,
    ai_generated: bool = True,
) -> dict[str, Any]:
    """
    Append an audit entry and return it.

    Args:
        kind: event type, e.g. "review_note", "draft_email", "digest".
        timestamp: ISO timestamp (caller supplies it; the store stays pure).
        output: the generated text; only a short preview is retained.
    """
    global _counter
    preview = (output or "").strip().replace("\n", " ")
    if len(preview) > _PREVIEW_CHARS:
        preview = preview[:_PREVIEW_CHARS] + "…"
    with _lock:
        _counter += 1
        entry = {
            "id": _counter,
            "kind": kind,
            "timestamp": timestamp,
            "client_id": client_id,
            "client_name": client_name,
            "model": model,
            "preview": preview,
            "ai_generated": ai_generated,
        }
        _entries.append(entry)
        return entry


def recent(limit: int = 50) -> list[dict[str, Any]]:
    """Return up to ``limit`` most-recent entries, newest first."""
    limit = max(1, min(limit, _MAX_ENTRIES))
    with _lock:
        items = list(_entries)[-limit:]
    items.reverse()
    return items


def clear() -> None:
    """Drop all audit entries (used by the data-reset flow and tests)."""
    global _counter
    with _lock:
        _entries.clear()
        _counter = 0
