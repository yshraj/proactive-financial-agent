"""
Ingestion config: chunk sizes and the Qdrant collection name.
Aligns with System Architecture: dual-path ingestion (Postgres + Qdrant).

Tenant attribution comes from the request/job TenantContext (app.context);
the legacy ADVISER_ID env stamp has been removed.
"""
from __future__ import annotations

import os

# ---- Path B: Semantic index (Qdrant) ----
# Chunk size ~500 tokens (≈2000 chars), overlap 50 tokens (≈200 chars)
CHUNK_CHAR_SIZE = 2000
CHUNK_OVERLAP = 200


def _default_collection() -> str:
    """Collection per embedding provider: vector dims differ (384 vs 1536),
    so each provider owns its own collection unless QDRANT_COLLECTION pins
    an explicit name. Migration between them: scripts/reindex_embeddings.py.
    """
    explicit = (os.environ.get("QDRANT_COLLECTION") or "").strip()
    if explicit:
        return explicit
    provider = (os.environ.get("EMBEDDINGS_PROVIDER") or "fastembed").strip().lower()
    return "client_memory" if provider == "openai" else "client_memory_bge384"


QDRANT_COLLECTION = _default_collection()
