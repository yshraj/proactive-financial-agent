"""
Ingestion config: chunk sizes, Qdrant collection, and LLM extraction schema.
Aligns with System Architecture: dual-path ingestion (Postgres + Qdrant).
"""
from __future__ import annotations

import os

# ---- Path B: Semantic index (Qdrant) ----
# Chunk size ~500 tokens (≈2000 chars), overlap 50 tokens (≈200 chars)
CHUNK_CHAR_SIZE = 2000
CHUNK_OVERLAP = 200
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "client_memory")

# ---- Path A: LLM extraction ----
# Optional: adviser_id to attach to new clients (from env)
ADVISER_ID = os.environ.get("ADVISER_ID")  # UUID string or None
