"""
Settings API: clear this workspace's data (Postgres + Qdrant) for demo reset.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.context import TenantContext
from app.db import get_cursor
from app.deps import current_tenant
from app.security import data_reset_enabled, limiter
from app.services import agent_runs, audit, conversations, jobs, storage
from app.services.cache import invalidate_all_ai_caches
from app.services.safety import public_error_message
from app.services.sample_data import build_sample_dataset
from app.services.vector_store import delete_org_points

logger = logging.getLogger("jarvis.settings")
router = APIRouter()


@router.post("/clear-data")
@limiter.limit("3/hour")
def clear_all_data(
    request: Request,
    response: Response,  # slowapi injects X-RateLimit headers (headers_enabled)
    ctx: TenantContext = Depends(current_tenant),
):
    """
    Remove THIS WORKSPACE's clients, alerts, document metadata, stored files,
    and Qdrant vectors. Destructive: requires ALLOW_DATA_RESET=true (and is
    disabled in production unless ALLOW_DATA_RESET=force). Other tenants'
    data is untouched; the immutable audit log survives by design.
    """
    if not data_reset_enabled():
        raise HTTPException(
            status_code=403,
            detail="Data reset is disabled. Set ALLOW_DATA_RESET=true to enable it.",
        )
    logger.warning(
        "[settings] clear-data invoked for org %s — wiping clients, alerts, documents, vectors",
        ctx.org_id,
    )
    # The wipe must leave a durable record; fail closed if audit is down.
    audit.record_event(
        action="data.cleared",
        resource_type="workspace",
        resource_id=ctx.org_id,
        required=True,
    )
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM alerts WHERE org_id = %s", (ctx.org_id,))
            cur.execute("DELETE FROM clients WHERE org_id = %s", (ctx.org_id,))
            cur.execute("DELETE FROM ingested_documents WHERE org_id = %s", (ctx.org_id,))
        # Clear this org's caches, review register, conversations, and jobs.
        invalidate_all_ai_caches()
        audit.clear()
        conversations.clear()
        jobs.clear()
        agent_runs.clear()
        storage.delete_org_documents(ctx.org_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=public_error_message("postgres_clear", e),
        ) from e

    # Remove this org's vectors only (never the shared collection).
    if os.environ.get("QDRANT_URL"):
        try:
            delete_org_points(ctx.org_id)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=public_error_message("qdrant_clear", e),
            ) from e

    return {"ok": True, "message": "Workspace data cleared (clients, alerts, ingested documents, vector index)."}


@router.post("/load-sample-data")
@limiter.limit("10/hour")
def load_sample_data(
    request: Request,
    response: Response,  # slowapi injects X-RateLimit headers (headers_enabled)
    ctx: TenantContext = Depends(current_tenant),
):
    """
    Populate the workspace with a demo dataset (clients + alerts) for onboarding.
    Only loads when the book is empty so it cannot create duplicate demo clients;
    callers should clear data first to reload.
    """
    try:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM clients WHERE org_id = %s", (ctx.org_id,))
            existing = cur.fetchone()["n"] or 0
        if existing:
            return {
                "loaded": False,
                "message": "Workspace already has data. Clear it first to load the demo set.",
                "clients": 0,
                "alerts": 0,
            }

        dataset = build_sample_dataset(datetime.now().date())
        clients_inserted = 0
        alerts_inserted = 0
        with get_cursor(commit=True) as cur:
            for client in dataset:
                cur.execute(
                    """
                    INSERT INTO clients
                        (org_id, full_name, retirement_target_age, risk_score,
                         total_assets, cash_savings, last_review_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::date)
                    RETURNING id
                    """,
                    (
                        ctx.org_id,
                        client["full_name"],
                        client.get("retirement_target_age"),
                        client.get("risk_score"),
                        client.get("total_assets"),
                        client.get("cash_savings"),
                        client.get("last_review_date"),
                    ),
                )
                client_id = cur.fetchone()["id"]
                clients_inserted += 1
                for alert in client.get("alerts", []):
                    cur.execute(
                        """
                        INSERT INTO alerts
                            (org_id, client_id, trigger_date, type, priority, title, description)
                        VALUES (%s, %s, %s::date, %s, %s, %s, %s)
                        """,
                        (
                            ctx.org_id,
                            client_id,
                            alert["trigger_date"],
                            alert["type"],
                            alert["priority"],
                            alert.get("title"),
                            alert.get("description"),
                        ),
                    )
                    alerts_inserted += 1
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=public_error_message("load_sample_data", e),
        ) from e

    invalidate_all_ai_caches()
    audit.record_event(
        action="sample_data.loaded",
        resource_type="workspace",
        resource_id=ctx.org_id,
        metadata={"clients": clients_inserted, "alerts": alerts_inserted},
    )
    return {
        "loaded": True,
        "message": f"Loaded {clients_inserted} demo clients and {alerts_inserted} alerts.",
        "clients": clients_inserted,
        "alerts": alerts_inserted,
    }
