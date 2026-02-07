"""
Settings API: clear all data (Postgres + Qdrant) for demo reset.
"""
import os

from fastapi import APIRouter, HTTPException

from app.db import get_cursor
from app.services.cache import delete_prefix
from app.services.config import QDRANT_COLLECTION

router = APIRouter()


@router.post("/clear-data")
def clear_all_data():
    """
    Remove all clients, alerts, ingested document metadata, and Qdrant vectors.
    Use for demo reset. Order: alerts (FK) -> clients -> ingested_documents; then clear Qdrant collection.
    """
    try:
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM alerts")
            cur.execute("DELETE FROM clients")
            cur.execute("DELETE FROM ingested_documents")
        # Clear in-memory caches (brief, draft, chat, extract)
        delete_prefix("brief:")
        delete_prefix("draft:")
        delete_prefix("chat:")
        delete_prefix("extract:")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear Postgres data: {e}") from e

    # Recreate Qdrant collection (delete + create) to clear all vectors
    url = os.environ.get("QDRANT_URL")
    api_key = os.environ.get("QDRANT_API_KEY") or None
    if url:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            client = QdrantClient(url=url, api_key=api_key)
            try:
                client.delete_collection(QDRANT_COLLECTION)
            except Exception:
                pass  # Collection may not exist
            client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to clear Qdrant: {e}") from e

    return {"ok": True, "message": "All data cleared (clients, alerts, ingested documents, vector index)."}
