"""
Agent run + step persistence (the durable record behind the agent runtime).

A run is one execution of the agent graph (kind ``copilot`` or ``brief``),
executed by the worker through the job queue. Steps are the real per-node
timeline — plan, each tool call, synthesis, review — that the frontend polls
(replacing the simulated thinking card) and that later powers audit/replay.

Everything here is org-scoped through the ambient/explicit TenantContext,
exactly like services/jobs.py; RLS backstops every query.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from app.context import TenantContext, get_current_tenant

# Run lifecycle states.
PENDING = "PENDING"
RUNNING = "RUNNING"
DONE = "DONE"
ERROR = "ERROR"

KINDS = ("copilot", "brief")


def _require_ctx(ctx: Optional[TenantContext]) -> TenantContext:
    tenant = ctx or get_current_tenant()
    if tenant is None:
        raise RuntimeError("agent runs require a tenant context")
    return tenant


def _jsonb(value: Any) -> Optional[str]:
    return json.dumps(value) if value is not None else None


def _load_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _run_from_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(r["id"]),
        "org_id": str(r["org_id"]),
        "user_id": str(r["user_id"]) if r.get("user_id") else None,
        "kind": r["kind"],
        "status": r["status"],
        "input": _load_json(r.get("input")) or {},
        "output": _load_json(r.get("output")),
        "state": _load_json(r.get("state")),
        "error": r.get("error"),
        "conversation_id": str(r["conversation_id"]) if r.get("conversation_id") else None,
        "client_id": str(r["client_id"]) if r.get("client_id") else None,
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
        "finished_at": r["finished_at"].isoformat() if r.get("finished_at") else None,
    }


def _step_from_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": int(r["seq"]),
        "node": r["node"],
        "label": r.get("label") or "",
        "status": r["status"],
        "detail": _load_json(r.get("detail")),
        "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
        "finished_at": r["finished_at"].isoformat() if r.get("finished_at") else None,
    }


def create(
    *,
    kind: str,
    input_payload: dict[str, Any],
    conversation_id: Optional[str] = None,
    client_id: Optional[str] = None,
    ctx: Optional[TenantContext] = None,
) -> dict[str, Any]:
    """Insert a PENDING run and return it."""
    from app.db import get_cursor

    if kind not in KINDS:
        raise ValueError(f"Unknown agent run kind {kind!r}")
    tenant = _require_ctx(ctx)
    run_id = str(uuid.uuid4())
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute(
            """
            INSERT INTO agent_runs (id, org_id, user_id, kind, input, conversation_id, client_id)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING *
            """,
            (
                run_id,
                tenant.org_id,
                tenant.user_id,
                kind,
                json.dumps(input_payload or {}),
                conversation_id,
                client_id,
            ),
        )
        row = cur.fetchone()
    return _run_from_row(row)


def get(run_id: str, *, ctx: Optional[TenantContext] = None) -> Optional[dict[str, Any]]:
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    try:
        with get_cursor(ctx=tenant) as cur:
            cur.execute(
                "SELECT * FROM agent_runs WHERE id = %s::uuid AND org_id = %s",
                (run_id, tenant.org_id),
            )
            row = cur.fetchone()
    except Exception:
        return None  # non-UUID ids resolve to "not found", not a 500
    return _run_from_row(row) if row else None


def get_steps(run_id: str, *, ctx: Optional[TenantContext] = None) -> list[dict[str, Any]]:
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    try:
        with get_cursor(ctx=tenant) as cur:
            cur.execute(
                """
                SELECT seq, node, label, status, detail, started_at, finished_at
                FROM agent_steps
                WHERE run_id = %s::uuid AND org_id = %s
                ORDER BY seq
                """,
                (run_id, tenant.org_id),
            )
            rows = cur.fetchall()
    except Exception:
        return []
    return [_step_from_row(r) for r in rows]


def mark_running(run_id: str, *, ctx: Optional[TenantContext] = None) -> None:
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute(
            """
            UPDATE agent_runs
            SET status = %s, started_at = COALESCE(started_at, NOW()), error = NULL
            WHERE id = %s::uuid AND org_id = %s
            """,
            (RUNNING, run_id, tenant.org_id),
        )


def finish(
    run_id: str, *, output: dict[str, Any], ctx: Optional[TenantContext] = None
) -> None:
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute(
            """
            UPDATE agent_runs
            SET status = %s, output = %s::jsonb, finished_at = NOW()
            WHERE id = %s::uuid AND org_id = %s
            """,
            (DONE, json.dumps(output), run_id, tenant.org_id),
        )


def fail(run_id: str, *, error: str, ctx: Optional[TenantContext] = None) -> None:
    """Mark the run failed. ``error`` must already be public-safe copy."""
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute(
            """
            UPDATE agent_runs
            SET status = %s, error = %s, finished_at = NOW()
            WHERE id = %s::uuid AND org_id = %s
            """,
            (ERROR, error, run_id, tenant.org_id),
        )


def save_state(
    run_id: str, *, state: dict[str, Any], ctx: Optional[TenantContext] = None
) -> None:
    """Checkpoint the latest graph state (best-effort; replay/debug record)."""
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute(
            "UPDATE agent_runs SET state = %s::jsonb WHERE id = %s::uuid AND org_id = %s",
            (_jsonb(state), run_id, tenant.org_id),
        )


def add_step(
    run_id: str,
    *,
    seq: int,
    node: str,
    label: str,
    detail: Optional[dict[str, Any]] = None,
    ctx: Optional[TenantContext] = None,
) -> None:
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute(
            """
            INSERT INTO agent_steps (run_id, org_id, seq, node, label, status, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (run_id, tenant.org_id, seq, node, label, RUNNING, _jsonb(detail)),
        )


def finish_step(
    run_id: str,
    *,
    seq: int,
    status: str = DONE,
    detail: Optional[dict[str, Any]] = None,
    ctx: Optional[TenantContext] = None,
) -> None:
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        if detail is not None:
            cur.execute(
                """
                UPDATE agent_steps
                SET status = %s, detail = %s::jsonb, finished_at = NOW()
                WHERE run_id = %s::uuid AND org_id = %s AND seq = %s
                """,
                (status, json.dumps(detail), run_id, tenant.org_id, seq),
            )
        else:
            cur.execute(
                """
                UPDATE agent_steps
                SET status = %s, finished_at = NOW()
                WHERE run_id = %s::uuid AND org_id = %s AND seq = %s
                """,
                (status, run_id, tenant.org_id, seq),
            )


def clear(*, ctx: Optional[TenantContext] = None) -> None:
    """Drop this org's agent runs (data-reset flow); steps cascade."""
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute("DELETE FROM agent_runs WHERE org_id = %s", (tenant.org_id,))
