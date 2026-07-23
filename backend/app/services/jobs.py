"""
Durable background-job queue (Postgres).

Replaces the in-memory registry: jobs survive restarts, and worker drains
(app/worker.py — event-driven: triggered after each enqueue and by the
scheduled safety net) claim work with ``FOR UPDATE SKIP LOCKED`` via the
SECURITY DEFINER ``claim_next_job()`` function — no broker, no poll loop
(production-readiness RFC, D4).

Lifecycle: PENDING -> PROCESSING -> DONE | ERROR. A PROCESSING job whose lock
went stale (worker died mid-job) is re-claimed until ``max_attempts``, then
failed by the sweeper. Handlers must therefore be idempotent — ingestion is
keyed by (org_id, content_hash).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.context import TenantContext, get_current_tenant, system_context

logger = logging.getLogger("jarvis.jobs")

# Lifecycle states for a job.
PENDING = "PENDING"
PROCESSING = "PROCESSING"
DONE = "DONE"
ERROR = "ERROR"

# A PROCESSING job with a lock older than this is considered orphaned.
STALE_LOCK_SECONDS = 600


def _job_from_row(r: dict[str, Any]) -> dict[str, Any]:
    payload = r.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    return {
        "id": str(r["id"]),
        "org_id": str(r["org_id"]),
        "kind": r["kind"],
        "filename": r.get("filename"),
        "status": r["status"],
        "progress": int(r.get("progress") or 0),
        "message": r.get("message") or "",
        "document_id": str(r["document_id"]) if r.get("document_id") else None,
        "error": r.get("error"),
        "attempts": int(r.get("attempts") or 0),
        "max_attempts": int(r.get("max_attempts") or 3),
        "payload": payload or {},
    }


def _require_ctx(ctx: Optional[TenantContext]) -> TenantContext:
    tenant = ctx or get_current_tenant()
    if tenant is None:
        raise RuntimeError("jobs require a tenant context")
    return tenant


def create(
    job_id: str,
    *,
    kind: str,
    filename: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
    document_id: Optional[str] = None,
    ctx: Optional[TenantContext] = None,
) -> dict[str, Any]:
    """Enqueue a new job in the PENDING state and return it."""
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute(
            """
            INSERT INTO jobs (id, org_id, kind, filename, payload, document_id)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            RETURNING *
            """,
            (
                job_id,
                tenant.org_id,
                kind,
                filename,
                json.dumps(payload or {}),
                document_id,
            ),
        )
        row = cur.fetchone()
    return _job_from_row(row)


def update(
    job_id: str, *, ctx: Optional[TenantContext] = None, **fields: Any
) -> Optional[dict[str, Any]]:
    """Patch a job's mutable fields. Returns the updated job, or None."""
    from app.db import get_cursor

    allowed = ("status", "progress", "message", "document_id", "error", "filename")
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get(job_id, ctx=ctx)
    tenant = _require_ctx(ctx)
    set_sql = ", ".join(f"{col} = %s" for col in updates)
    params: list[Any] = list(updates.values())
    params.extend([job_id, tenant.org_id])
    with get_cursor(commit=True, ctx=tenant) as cur:
        # sql-ok: set_sql columns come from the `allowed` tuple above
        cur.execute(
            f"UPDATE jobs SET {set_sql} WHERE id = %s AND org_id = %s RETURNING *",
            tuple(params),
        )
        row = cur.fetchone()
    return _job_from_row(row) if row else None


def get(job_id: str, *, ctx: Optional[TenantContext] = None) -> Optional[dict[str, Any]]:
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(ctx=tenant) as cur:
        cur.execute(
            "SELECT * FROM jobs WHERE id = %s AND org_id = %s", (job_id, tenant.org_id)
        )
        row = cur.fetchone()
    return _job_from_row(row) if row else None


def clear(*, ctx: Optional[TenantContext] = None) -> None:
    """Delete this org's finished/queued jobs (data-reset flow)."""
    from app.db import get_cursor

    tenant = _require_ctx(ctx)
    with get_cursor(commit=True, ctx=tenant) as cur:
        cur.execute("DELETE FROM jobs WHERE org_id = %s", (tenant.org_id,))


# ---------------------------------------------------------------------------
# Worker-side operations (cross-org claim via SECURITY DEFINER functions).
# ---------------------------------------------------------------------------


def claim_next(worker_name: str) -> Optional[dict[str, Any]]:
    """Claim the next runnable job (PENDING, or PROCESSING with a stale lock).

    Runs without a tenant context: claim_next_job() is SECURITY DEFINER. The
    returned job carries org_id; callers must process it under
    ``system_context(job['org_id'])``.
    """
    from app.db import get_cursor

    bootstrap = system_context("")  # no org GUC: function is security definer
    with get_cursor(commit=True, ctx=bootstrap) as cur:
        cur.execute(
            "SELECT * FROM claim_next_job(%s, %s)", (worker_name, STALE_LOCK_SECONDS)
        )
        row = cur.fetchone()
    return _job_from_row(row) if row else None


def sweep_exhausted() -> int:
    """Fail PROCESSING jobs whose lock is stale and retries are exhausted."""
    from app.db import get_cursor

    bootstrap = system_context("")
    with get_cursor(commit=True, ctx=bootstrap) as cur:
        cur.execute("SELECT fail_exhausted_jobs(%s) AS n", (STALE_LOCK_SECONDS,))
        row = cur.fetchone()
    return int(row["n"] or 0) if row else 0


def has_runnable() -> bool:
    """True when any job is claimable (PENDING, or PROCESSING with a stale,
    retryable lock).

    Lets a budget-exhausted drain decide whether handing off to a fresh
    invocation is actually needed. SECURITY DEFINER (like claim_next) because
    the worker runs without a tenant context.
    """
    from app.db import get_cursor

    bootstrap = system_context("")
    with get_cursor(ctx=bootstrap) as cur:
        cur.execute("SELECT runnable_jobs_exist(%s) AS has_work", (STALE_LOCK_SECONDS,))
        row = cur.fetchone()
    return bool(row and row["has_work"])


def count_runnable() -> int:
    """Current queue depth (PENDING + stale-but-retryable PROCESSING).

    Logged after each drain and surfaced as the KritiFin/QueueDepth CloudWatch
    metric — the agreed signal for when the Postgres queue needs replacing
    with SQS (sustained depth > ~10). SECURITY DEFINER like claim_next().
    """
    from app.db import get_cursor

    bootstrap = system_context("")
    with get_cursor(ctx=bootstrap) as cur:
        cur.execute("SELECT runnable_jobs_count(%s) AS depth", (STALE_LOCK_SECONDS,))
        row = cur.fetchone()
    return int(row["depth"] or 0) if row else 0
