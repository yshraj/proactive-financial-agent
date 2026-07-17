"""
Durable, user-owned conversation memory for Ask Jarvis (multi-turn chat).

Postgres-backed (replaces the in-memory OrderedDict): threads survive restarts,
are scoped to the workspace by RLS, and are owned by the creating user — a
conversation id from another user/org resolves as "not found", closing the
unowned-conversation continuation hole.

The message-windowing and history-formatting helpers remain pure.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from app.context import TenantContext, get_current_tenant

# Messages kept per conversation when building prompt history.
_MAX_MESSAGES = 20


def _require_ctx(ctx: Optional[TenantContext]) -> TenantContext:
    tenant = ctx or get_current_tenant()
    if tenant is None:
        raise RuntimeError("conversations require a tenant context")
    return tenant


def _owned_filter_sql(tenant: TenantContext, alias: str = "") -> tuple[str, list[Any]]:
    """Conversations are visible to their creator; demo/service contexts share
    the workspace thread pool (user_id IS NULL rows)."""
    p = f"{alias}." if alias else ""
    if tenant.user_id:
        return f"{p}org_id = %s AND {p}user_id = %s", [tenant.org_id, tenant.user_id]
    return f"{p}org_id = %s AND {p}user_id IS NULL", [tenant.org_id]


def create(*, client_id: Optional[str] = None, ctx: Optional[TenantContext] = None) -> str:
    """Create a new conversation and return its id."""
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    conv_id = str(uuid.uuid4())
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute(
            """
            INSERT INTO conversations (id, org_id, user_id, client_id)
            VALUES (%s, %s, %s, %s)
            """,
            (conv_id, tenant.org_id, tenant.user_id, client_id),
        )
    return conv_id


def exists(conversation_id: str, *, ctx: Optional[TenantContext] = None) -> bool:
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    where, params = _owned_filter_sql(tenant)
    try:
        with get_cursor(ctx=tenant) as cur:
            # sql-ok: `where` is built from fixed column predicates in _owned_filter_sql
            cur.execute(
                f"SELECT 1 FROM conversations WHERE id = %s::uuid AND {where}",
                tuple([conversation_id] + params),
            )
            return cur.fetchone() is not None
    except Exception:
        # Non-UUID ids (or storage errors) mean "no such conversation".
        return False


def add_message(
    conversation_id: str, role: str, content: str, *, ctx: Optional[TenantContext] = None
) -> None:
    """Append a message to an owned conversation (no-op if not owned)."""
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    where, params = _owned_filter_sql(tenant)
    with get_cursor(commit=True, ctx=tenant) as cur:
        # sql-ok: `where` is built from fixed column predicates in _owned_filter_sql
        cur.execute(
            f"SELECT id FROM conversations WHERE id = %s::uuid AND {where}",
            tuple([conversation_id] + params),
        )
        if cur.fetchone() is None:
            return
        cur.execute(
            """
            INSERT INTO conversation_messages (conversation_id, org_id, role, content)
            VALUES (%s, %s, %s, %s)
            """,
            (conversation_id, tenant.org_id, role, content),
        )
        cur.execute(
            "UPDATE conversations SET updated_at = NOW() WHERE id = %s", (conversation_id,)
        )


def get_messages(
    conversation_id: str, limit: int = _MAX_MESSAGES, *, ctx: Optional[TenantContext] = None
) -> list[dict[str, str]]:
    """Return up to ``limit`` most-recent messages (oldest first)."""
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    where, params = _owned_filter_sql(tenant, alias="c")
    try:
        with get_cursor(ctx=tenant) as cur:
            # sql-ok: `where` is built from fixed column predicates in _owned_filter_sql
            cur.execute(
                f"""
                SELECT m.role, m.content
                FROM conversation_messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE m.conversation_id = %s::uuid AND {where}
                ORDER BY m.id DESC
                LIMIT %s
                """,
                tuple([conversation_id] + params + [limit]),
            )
            rows = cur.fetchall()
    except Exception:
        return []
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


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


def clear(*, ctx: Optional[TenantContext] = None) -> None:
    """Drop this org's conversations (data-reset flow)."""
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute("DELETE FROM conversations WHERE org_id = %s", (tenant.org_id,))
