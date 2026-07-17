"""
Durable, tenant-scoped audit trail (Postgres).

Two stores (production-readiness RFC, D9):

- ``audit_log`` — the append-only legal record: who / what / when / where /
  before / after, with request correlation. The runtime DB role holds
  INSERT+SELECT only and a trigger blocks UPDATE/DELETE, so entries survive
  restarts and cannot be rewritten.
- ``ai_outputs`` — the mutable human-review register that powers the existing
  audit/approve UI. Approvals update the register *and* append an
  ``ai.output.approved`` event to the log; the log itself is never mutated.

Failure policy: recording an AI output or event must not take the product
down — failures are logged (and surface in Sentry via the error log handler).
Destructive operations that MUST be audited call :func:`record_event` with
``required=True``, which re-raises so the operation fails closed.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Optional

from app.context import TenantContext, get_current_tenant, get_request_id

logger = logging.getLogger("jarvis.audit")

# Preview length for stored output (avoid persisting full client content).
_PREVIEW_CHARS = 160

# Event action taxonomy (verb.noun). Keep in sync with docs/runbooks/audit.md.
AI_GENERATED_ACTIONS = {
    "digest": "ai.digest.generated",
    "draft_email": "ai.draft_email.generated",
    "review_note": "ai.review_note.generated",
    "brief": "ai.brief.generated",
    "chat": "ai.chat.answered",
    "summary": "ai.summary.generated",
}


def _preview(output: Optional[str]) -> str:
    preview = (output or "").strip().replace("\n", " ")
    if len(preview) > _PREVIEW_CHARS:
        preview = preview[:_PREVIEW_CHARS] + "…"
    return preview


def _json_or_none(value: Optional[Mapping[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return json.dumps({"unserializable": str(value)})


def _ctx(ctx: Optional[TenantContext]) -> TenantContext:
    resolved = ctx or get_current_tenant()
    if resolved is None:
        raise RuntimeError("audit requires a tenant context (request or job scope)")
    return resolved


def record_event(
    *,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    client_id: Optional[str] = None,
    before: Optional[Mapping[str, Any]] = None,
    after: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    model: Optional[str] = None,
    prompt_version: Optional[str] = None,
    actor_type: Optional[str] = None,
    ctx: Optional[TenantContext] = None,
    required: bool = False,
) -> Optional[int]:
    """Append an event to the immutable audit log. Returns the event id.

    With ``required=False`` (default) failures are swallowed after logging so a
    broken audit path cannot take reads down. Destructive/compliance-critical
    callers pass ``required=True`` to fail closed.
    """
    from app.db import get_cursor

    try:
        tenant = _ctx(ctx)
        resolved_actor = actor_type or (
            "user" if tenant.user_id else ("ai" if action.startswith("ai.") else tenant.role)
        )
        if resolved_actor not in ("user", "system", "ai", "service", "demo"):
            resolved_actor = "system"
        with get_cursor(commit=True, ctx=tenant) as cur:
            cur.execute(
                """
                INSERT INTO audit_log
                    (org_id, actor_user_id, actor_type, action, resource_type,
                     resource_id, client_id, request_id, model, prompt_version,
                     before, after, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb)
                RETURNING id
                """,
                (
                    tenant.org_id,
                    tenant.user_id,
                    resolved_actor,
                    action,
                    resource_type,
                    resource_id,
                    client_id,
                    tenant.request_id or get_request_id(),
                    model,
                    prompt_version,
                    _json_or_none(before),
                    _json_or_none(after),
                    _json_or_none(metadata),
                ),
            )
            row = cur.fetchone()
        return int(row["id"]) if row else None
    except Exception:
        logger.exception("audit event write failed: action=%s", action)
        if required:
            raise
        return None


def record(
    *,
    kind: str,
    timestamp: Optional[str] = None,  # kept for call-site compatibility; DB stamps time
    client_id: Optional[str] = None,
    client_name: Optional[str] = None,
    model: Optional[str] = None,
    output: Optional[str] = None,
    ai_generated: bool = True,
    prompt_version: Optional[str] = None,
    ctx: Optional[TenantContext] = None,
) -> Optional[dict[str, Any]]:
    """Record an AI output: review-register row + immutable audit event.

    Returns the register entry (API shape) or None if persistence failed.
    """
    from app.db import get_cursor

    del timestamp  # the database is the single source of event time
    try:
        tenant = _ctx(ctx)
        preview = _preview(output)
        with get_cursor(commit=True, ctx=tenant) as cur:
            cur.execute(
                """
                INSERT INTO ai_outputs
                    (org_id, kind, client_id, client_name, model, prompt_version,
                     preview, ai_generated, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    tenant.org_id,
                    kind,
                    client_id,
                    client_name,
                    model,
                    prompt_version,
                    preview,
                    ai_generated,
                    tenant.user_id,
                ),
            )
            row = cur.fetchone()
        entry_id = int(row["id"])
        record_event(
            action=AI_GENERATED_ACTIONS.get(kind, f"ai.{kind}.generated"),
            resource_type="ai_output",
            resource_id=str(entry_id),
            client_id=client_id,
            metadata={"client_name": client_name, "ai_generated": ai_generated},
            model=model,
            prompt_version=prompt_version,
            actor_type="ai",
            ctx=tenant,
        )
        return {
            "id": entry_id,
            "kind": kind,
            "timestamp": row["created_at"].isoformat(),
            "client_id": client_id,
            "client_name": client_name,
            "model": model,
            "preview": preview,
            "ai_generated": ai_generated,
            "reviewed": False,
            "reviewed_at": None,
        }
    except Exception:
        logger.exception("ai_outputs write failed: kind=%s", kind)
        return None


def _entry_from_row(r: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": int(r["id"]),
        "kind": r["kind"],
        "timestamp": r["created_at"].isoformat() if r.get("created_at") else "",
        "client_id": str(r["client_id"]) if r.get("client_id") else None,
        "client_name": r.get("client_name"),
        "model": r.get("model"),
        "preview": r.get("preview") or "",
        "ai_generated": bool(r.get("ai_generated")),
        "reviewed": r.get("reviewed_at") is not None,
        "reviewed_at": r["reviewed_at"].isoformat() if r.get("reviewed_at") else None,
    }


def recent(
    limit: int = 50, *, offset: int = 0, ctx: Optional[TenantContext] = None
) -> list[dict[str, Any]]:
    """Most-recent AI outputs for this org, newest first (paginated)."""
    from app.db import get_cursor

    tenant = _ctx(ctx)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    with get_cursor(ctx=tenant) as cur:
        cur.execute(
            """
            SELECT id, kind, created_at, client_id, client_name, model, preview,
                   ai_generated, reviewed_at
            FROM ai_outputs
            WHERE org_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (tenant.org_id, limit, offset),
        )
        rows = cur.fetchall()
    return [_entry_from_row(r) for r in rows]


def approve(
    entry_id: int,
    reviewed_at: Optional[str] = None,  # compatibility; DB stamps review time
    *,
    ctx: Optional[TenantContext] = None,
) -> Optional[dict[str, Any]]:
    """Mark an AI output as human-reviewed and append the approval event."""
    from app.db import get_cursor

    del reviewed_at
    tenant = _ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute(
            """
            UPDATE ai_outputs
            SET reviewed_by = %s, reviewed_at = COALESCE(reviewed_at, NOW())
            WHERE id = %s AND org_id = %s
            RETURNING id, kind, created_at, client_id, client_name, model, preview,
                      ai_generated, reviewed_at
            """,
            (tenant.user_id, entry_id, tenant.org_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    record_event(
        action="ai.output.approved",
        resource_type="ai_output",
        resource_id=str(entry_id),
        client_id=str(row["client_id"]) if row.get("client_id") else None,
        metadata={"kind": row.get("kind")},
        actor_type="user" if tenant.user_id else None,
        ctx=tenant,
    )
    return _entry_from_row(row)


def events(
    limit: int = 100,
    *,
    offset: int = 0,
    action: Optional[str] = None,
    client_id: Optional[str] = None,
    ctx: Optional[TenantContext] = None,
) -> list[dict[str, Any]]:
    """Paginated read of the immutable event log for this org."""
    from app.db import get_cursor

    tenant = _ctx(ctx)
    limit = max(1, min(int(limit), 500))
    sql = """
        SELECT id, actor_user_id, actor_type, action, resource_type, resource_id,
               client_id, request_id, model, prompt_version, metadata, created_at
        FROM audit_log
        WHERE org_id = %s
    """
    params: list[Any] = [tenant.org_id]
    if action:
        sql += " AND action = %s"
        params.append(action)
    if client_id:
        sql += " AND client_id = %s"
        params.append(client_id)
    sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
    params.extend([limit, max(0, int(offset))])
    with get_cursor(ctx=tenant) as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": int(r["id"]),
                "actor_user_id": str(r["actor_user_id"]) if r.get("actor_user_id") else None,
                "actor_type": r.get("actor_type"),
                "action": r.get("action"),
                "resource_type": r.get("resource_type"),
                "resource_id": r.get("resource_id"),
                "client_id": str(r["client_id"]) if r.get("client_id") else None,
                "request_id": r.get("request_id"),
                "model": r.get("model"),
                "prompt_version": r.get("prompt_version"),
                "metadata": r.get("metadata"),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else "",
            }
        )
    return out


def clear(*, ctx: Optional[TenantContext] = None) -> None:
    """Org-scoped reset of the *review register* only.

    The immutable ``audit_log`` is intentionally not (and cannot be) deleted by
    the runtime role — the record of what happened survives data resets.
    """
    from app.db import get_cursor

    tenant = _ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute("DELETE FROM ai_outputs WHERE org_id = %s", (tenant.org_id,))
