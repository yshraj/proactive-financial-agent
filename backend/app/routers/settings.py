"""
Settings API: clear all data (Postgres + Qdrant) for demo reset.
"""
import logging

from fastapi import APIRouter, HTTPException, Request

from app.db import get_cursor
from app.security import data_reset_enabled, limiter
from app.services.cache import invalidate_all_ai_caches
from app.services.config import QDRANT_COLLECTION
from app.services.safety import public_error_message
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
