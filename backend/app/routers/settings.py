"""
Settings API: clear all data (Postgres + Qdrant) for demo reset.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from app.db import get_cursor
from app.security import data_reset_enabled, limiter
from app.services.cache import invalidate_all_ai_caches
from app.services.config import QDRANT_COLLECTION
from app.services.safety import public_error_message
from app.services.sample_data import build_sample_dataset
from app.services.vector_store import recreate_collection
import os

logger = logging.getLogger("jarvis.settings")
router = APIRouter()


@router.post("/clear-data")
@limiter.limit("3/hour")
def clear_all_data(request: Request):
    """
    Remove all clients, alerts, ingested document metadata, and Qdrant vectors.
    Destructive: requires ALLOW_DATA_RESET=true (in addition to the API key) so it
    cannot be triggered accidentally in production.
    Order: alerts (FK) -> clients -> ingested_documents; then clear Qdrant collection.
    """
    if not data_reset_enabled():
        raise HTTPException(
            status_code=403,
            detail="Data reset is disabled. Set ALLOW_DATA_RESET=true to enable it.",
        )
    logger.warning("[settings] clear-data invoked — wiping all clients, alerts, documents and vectors")
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM alerts")
            cur.execute("DELETE FROM clients")
            cur.execute("DELETE FROM ingested_documents")
        # Clear in-memory caches (brief, draft, chat, extract)
        invalidate_all_ai_caches()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=public_error_message("postgres_clear", e),
        ) from e

    # Recreate Qdrant collection when configured (delete + create clears all vectors)
    if os.environ.get("QDRANT_URL"):
        try:
            recreate_collection(QDRANT_COLLECTION)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=public_error_message("qdrant_clear", e),
            ) from e

    return {"ok": True, "message": "All data cleared (clients, alerts, ingested documents, vector index)."}


@router.post("/load-sample-data")
@limiter.limit("10/hour")
def load_sample_data(request: Request):
    """
    Populate the workspace with a demo dataset (clients + alerts) for onboarding.
    Only loads when the book is empty so it cannot create duplicate demo clients;
    callers should clear data first to reload.
    """
    try:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM clients")
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
                        (full_name, retirement_target_age, risk_score,
                         total_assets, cash_savings, last_review_date)
                    VALUES (%s, %s, %s, %s, %s, %s::date)
                    RETURNING id
                    """,
                    (
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
                            (client_id, trigger_date, type, priority, title, description)
                        VALUES (%s, %s::date, %s, %s, %s, %s)
                        """,
                        (
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
    return {
        "loaded": True,
        "message": f"Loaded {clients_inserted} demo clients and {alerts_inserted} alerts.",
        "clients": clients_inserted,
        "alerts": alerts_inserted,
    }
