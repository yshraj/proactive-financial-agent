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
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "client_memory")
