"""
In-memory conversation memory for Ask Jarvis (multi-turn chat threads).

Follows the same in-process convention as services/cache.py and services/audit.py
(not durable across restarts, acceptable for the current single-instance
deployment). Thread-safe; the message-windowing and history-formatting helpers
are pure and fully unit-testable.
"""
from __future__ import annotations

import threading
import uuid
from collections import OrderedDict, deque
from typing import Any

# Cap total conversations (LRU-evicted) and messages kept per conversation.
_MAX_CONVERSATIONS = 200
_MAX_MESSAGES = 20

_store: "OrderedDict[str, deque[dict[str, str]]]" = OrderedDict()
_lock = threading.Lock()


def create() -> str:
    """Create a new conversation and return its id."""
    conv_id = uuid.uuid4().hex
    with _lock:
        _store[conv_id] = deque(maxlen=_MAX_MESSAGES)
        _store.move_to_end(conv_id)
        _evict_if_needed()
    return conv_id


def exists(conversation_id: str) -> bool:
    with _lock:
        return conversation_id in _store


def add_message(conversation_id: str, role: str, content: str) -> None:
    """Append a message; creates the conversation if it does not exist yet."""
    with _lock:
        if conversation_id not in _store:
            _store[conversation_id] = deque(maxlen=_MAX_MESSAGES)
        _store[conversation_id].append({"role": role, "content": content})
        _store.move_to_end(conversation_id)
        _evict_if_needed()


def get_messages(conversation_id: str, limit: int = _MAX_MESSAGES) -> list[dict[str, str]]:
    """Return up to ``limit`` most-recent messages (oldest first)."""
    with _lock:
        msgs = list(_store.get(conversation_id, ()))
    return msgs[-limit:]


def _evict_if_needed() -> None:
    """Drop oldest conversations beyond the cap. Caller holds the lock."""
    while len(_store) > _MAX_CONVERSATIONS:
        _store.popitem(last=False)


def format_history(messages: list[dict[str, Any]], max_chars: int = 2000) -> str:
    """
    Render prior turns as a compact transcript for the prompt.

    Pure: no global state. Truncates to ``max_chars`` from the most recent end so
    the freshest context survives.
    """
    if not messages:
        return ""
    lines = []
    for m in messages:
        role = "Adviser" if m.get("role") == "user" else "Jarvis"
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = "…" + text[-max_chars:]
    return text


def clear() -> None:
    """Drop all conversations (used by the data-reset flow and tests)."""
    with _lock:
        _store.clear()
