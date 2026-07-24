"""
RAG retrieval, score filtering, and citation-ready context formatting.

Tenant isolation: :func:`search_qdrant` is the single search wrapper and it
REQUIRES an ``org_id`` — a filter-less (cross-tenant) vector search cannot be
expressed through this module. Points carry ``org_id`` in their payload
(services/vector_store.py) with a keyword payload index (is_tenant pattern).
"""
from __future__ import annotations

import os
from typing import Any, Optional

from app.services.config import QDRANT_COLLECTION
from app.services.embeddings import embed_texts
from app.services.safety import sanitize_rag_content

RAG_MIN_SCORE = float(os.environ.get("RAG_MIN_SCORE", "0.32"))
CHAT_RAG_LIMIT = 5
CHAT_CHUNK_CHARS = 1200
BRIEF_RAG_LIMIT = 8
BRIEF_CHUNK_CHARS = 1200
SOURCE_PREVIEW_CHARS = 280


def embed_query(text: str) -> list[float]:
    vectors = embed_texts([text])
    if not vectors:
        raise RuntimeError("Embedding failed")
    return vectors[0]


def search_qdrant(
    query_vector: list[float],
    *,
    org_id: str,
    limit: int = 5,
    client_id: Optional[str] = None,
    min_score: float = RAG_MIN_SCORE,
) -> list[Any]:
    """Return Qdrant points at or above min_score, up to limit.

    ``org_id`` is mandatory: every search is tenant-filtered. Raises ValueError
    when missing so a scoping bug fails loudly instead of leaking data.
    """
    if not org_id:
        raise ValueError("search_qdrant requires org_id (tenant isolation)")

    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from app.services.clients import get_qdrant_client
    from app.services.vector_store import ensure_payload_indexes, is_missing_index_error

    client = get_qdrant_client()
    must = [FieldCondition(key="org_id", match=MatchValue(value=org_id))]
    if client_id:
        must.append(FieldCondition(key="client_id", match=MatchValue(value=client_id)))
    query_filter = Filter(must=must)

    def _query():
        return client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
        )

    try:
        results = _query()
    except Exception as exc:
        if not is_missing_index_error(exc):
            raise
        # Collection predates the tenancy migration (no org_id/client_id
        # payload indexes): create them and retry once.
        ensure_payload_indexes(QDRANT_COLLECTION)
        results = _query()
    points = getattr(results, "points", None) or (
        list(results) if isinstance(results, (list, tuple)) else []
    )
    filtered = [p for p in points if float(getattr(p, "score", 1.0)) >= min_score]
    return filtered[:limit]


def format_rag_context(
    points: list[Any],
    *,
    chunk_chars: int = CHAT_CHUNK_CHARS,
    preview_chars: int = SOURCE_PREVIEW_CHARS,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Format retrieved chunks as numbered excerpts for LLM context.
    Returns (context_string, source_dicts for API response).
    """
    if not points:
        return "", []

    context_parts: list[str] = []
    sources: list[dict[str, Any]] = []

    for i, pt in enumerate(points, start=1):
        payload = getattr(pt, "payload", None) or {}
        content = sanitize_rag_content((payload.get("content") or "")[:chunk_chars])
        if not content.strip():
            continue
        client_name = payload.get("client_name") or "Unknown"
        doc_type = payload.get("doc_type") or ""
        date = payload.get("date") or ""
        score = round(float(getattr(pt, "score", 0.0)), 3)
        context_parts.append(
            f"[{i}] Client: {client_name} | {doc_type or 'Document'} | {date or 'undated'} | relevance={score}\n{content}"
        )
        preview = content[:preview_chars] + ("…" if len(content) > preview_chars else "")
        sources.append({
            "ref": i,
            "content": preview,
            "client_name": client_name,
            "doc_type": doc_type,
            "date": date,
            "relevance": score,
        })

    context = "\n\n---\n\n".join(context_parts)
    return context, sources


def brief_retrieval_query(client_name: str, alert_titles: list[str]) -> str:
    """Build a retrieval query from client identity and open alert titles."""
    terms = [client_name, "fact find", "meeting notes", "financial review"]
    for title in alert_titles[:4]:
        if title:
            terms.append(title[:60])
    return " ".join(terms)


def retrieve_for_chat(
    query: str,
    *,
    org_id: str,
    client_id: Optional[str] = None,
) -> tuple[str, list[dict[str, Any]]]:
    vector = embed_query(query)
    points = search_qdrant(vector, org_id=org_id, limit=CHAT_RAG_LIMIT, client_id=client_id)
    return format_rag_context(points, chunk_chars=CHAT_CHUNK_CHARS)


def retrieve_for_brief(
    client_name: str,
    alert_titles: list[str],
    *,
    org_id: str,
    client_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    query = brief_retrieval_query(client_name, alert_titles)
    vector = embed_query(query)
    points = search_qdrant(vector, org_id=org_id, limit=BRIEF_RAG_LIMIT, client_id=client_id)
    return format_rag_context(points, chunk_chars=BRIEF_CHUNK_CHARS)
