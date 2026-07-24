"""
Path B: Chunk text, add context, embed (fastembed local by default; OpenAI
legacy via EMBEDDINGS_PROVIDER=openai), upsert to the Qdrant collection.
Payload includes content + metadata for filtered vector search:
  - content, client_id, client_name, doc_type, date, topics (architecture)
  - document_id, filename, source_type, ingested_at (for metadata filters)
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.services.config import CHUNK_CHAR_SIZE, CHUNK_OVERLAP, QDRANT_COLLECTION

logger = logging.getLogger("jarvis.ingest")

# Payload fields stored for every chunk (use in query_filter for vector search):
#   client_id (str), client_name (str), doc_type (str), date (str YYYY-MM-DD), topics (list[str])
#   document_id (str), filename (str), source_type ("pdf"|"docx"), ingested_at (str ISO)
# Example filter: FieldCondition(key="client_id", match=MatchValue(value="uuid-here"))
# Example filter: FieldCondition(key="source_type", match=MatchValue(value="pdf"))


def chunk_text(text: str, chunk_size: int = CHUNK_CHAR_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks (char-based; ~500 tokens ≈ 2000 chars, 50 ≈ 200)."""
    if not text or len(text) <= chunk_size:
        return [text] if text and text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def _prefix_context(chunk: str, client_name: str, doc_date: Optional[str]) -> str:
    """Prepend 'Client Name: X | Date: Y' to chunk for better retrieval (architecture)."""
    date_part = f" | Date: {doc_date}" if doc_date else ""
    return f"Client Name: {client_name}{date_part}\n\n{chunk}"


def ensure_collection(collection: str = QDRANT_COLLECTION) -> None:
    """Create the collection for the configured embedding provider if missing.

    Idempotent and self-healing: first ingest after a provider switch (e.g.
    the fastembed migration) creates the right-sized collection instead of
    failing. Vector size comes from services.embeddings.
    """
    from qdrant_client.models import Distance, VectorParams

    from app.services import embeddings
    from app.services.clients import get_qdrant_client

    client = get_qdrant_client()
    try:
        if client.collection_exists(collection):
            return
        logger.info(
            "[qdrant] Creating collection %s (%d dims, %s)",
            collection, embeddings.vector_size(), embeddings.model_name(),
        )
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=embeddings.vector_size(), distance=Distance.COSINE),
        )
        ensure_payload_indexes(collection)
    except Exception:  # noqa: BLE001 - a race with another creator is fine
        logger.info("[qdrant] ensure_collection(%s): already present or racing", collection)


def upsert_to_qdrant(
    chunks: list[str],
    vectors: list[list[float]],
    client_id: str,
    doc_type: str = "Document",
    doc_date: Optional[str] = None,
    topics: Optional[list[str]] = None,
    *,
    org_id: Optional[str] = None,
    client_name: Optional[str] = None,
    document_id: Optional[str] = None,
    filename: Optional[str] = None,
    source_type: Optional[str] = None,
    ingested_at: Optional[str] = None,
    collection: str = QDRANT_COLLECTION,
) -> None:
    """
    Upsert chunk vectors into Qdrant with full metadata for filtered search.
    Filterable payload fields: org_id (tenant boundary), client_id, client_name,
    doc_type, date, topics, document_id, filename, source_type, ingested_at.
    """
    from qdrant_client.models import PointStruct

    from app.context import require_current_tenant
    from app.services.clients import get_qdrant_client

    resolved_org = org_id or require_current_tenant().org_id
    if not resolved_org:
        raise ValueError("upsert_to_qdrant requires an org_id (tenant isolation)")

    client = get_qdrant_client()
    topics = topics or []
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vec,
            payload={
                "content": content,
                "org_id": resolved_org,
                "client_id": client_id,
                "doc_type": doc_type,
                "date": doc_date or "",
                "topics": topics,
                "client_name": client_name or "",
                "document_id": document_id or "",
                "filename": filename or "",
                "source_type": source_type or "",
                "ingested_at": ingested_at or "",
            },
        )
        for content, vec in zip(chunks, vectors)
    ]
    logger.info(
        "[ingest] Qdrant upsert: collection=%s, points=%d, client_id=%s, doc_type=%s, filename=%s, source_type=%s",
        collection,
        len(points),
        client_id,
        doc_type,
        filename or "",
        source_type or "",
    )
    client.upsert(collection_name=collection, points=points)
    logger.info("[ingest] Qdrant upsert done: %d points in %s", len(points), collection)


def is_missing_index_error(exc: Exception) -> bool:
    """Qdrant Cloud rejects filters on unindexed payload fields with this 400.

    Happens when the collection predates the tenancy migration (indexes were
    never created). Callers self-heal by creating the indexes and retrying.
    """
    return "Index required but not found" in str(exc)


def ensure_payload_indexes(collection: str = QDRANT_COLLECTION) -> None:
    """Create keyword payload indexes for the fields every search filters on.

    org_id uses ``is_tenant=True`` (Qdrant's multitenancy optimisation) where
    the server version supports it; plain keyword indexes otherwise. Idempotent.
    """
    from qdrant_client.models import KeywordIndexParams

    from app.services.clients import get_qdrant_client

    client = get_qdrant_client()
    try:
        client.create_payload_index(
            collection_name=collection,
            field_name="org_id",
            field_schema=KeywordIndexParams(type="keyword", is_tenant=True),
        )
    except Exception:
        try:
            client.create_payload_index(
                collection_name=collection, field_name="org_id", field_schema="keyword"
            )
        except Exception:
            logger.info("org_id payload index already present or unsupported")
    try:
        client.create_payload_index(
            collection_name=collection, field_name="client_id", field_schema="keyword"
        )
    except Exception:
        logger.info("client_id payload index already present")


def delete_org_points(org_id: str, collection: str = QDRANT_COLLECTION) -> None:
    """Delete only this org's points (org-scoped data reset)."""
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    from app.services.clients import get_qdrant_client

    client = get_qdrant_client()
    selector = FilterSelector(
        filter=Filter(must=[FieldCondition(key="org_id", match=MatchValue(value=org_id))])
    )
    try:
        client.delete(collection_name=collection, points_selector=selector)
    except Exception as exc:
        if not is_missing_index_error(exc):
            raise
        # Collection predates the tenancy migration: create the payload
        # indexes it is missing, then retry once.
        logger.warning("[qdrant] org_id index missing on %s; creating and retrying", collection)
        ensure_payload_indexes(collection)
        client.delete(collection_name=collection, points_selector=selector)


def index_document_text(
    raw_text: str,
    client_id: str,
    client_name: str,
    doc_type: str = "Document",
    doc_date: Optional[str] = None,
    *,
    document_id: Optional[str] = None,
    filename: Optional[str] = None,
    source_type: Optional[str] = None,
    ingested_at: Optional[str] = None,
    topics: Optional[list[str]] = None,
) -> None:
    """
    Full Path B: chunk text, add context prefix, embed, upsert to Qdrant with metadata.
    All metadata is stored in payload for filtered vector search (client_id, doc_type, date,
    document_id, filename, source_type, ingested_at, topics).
    """
    if not raw_text or not raw_text.strip():
        logger.info("[ingest] Vector index skipped: no text")
        return
    from app.services.safety import sanitize_rag_content

    chunks = chunk_text(raw_text)
    if not chunks:
        logger.info("[ingest] Vector index skipped: no chunks")
        return
    logger.info(
        "[ingest] Vector index: %d chunks for client_id=%s, doc_type=%s",
        len(chunks),
        client_id,
        doc_type,
    )
    # Sanitize before embed so adversarial PDFs are not stored verbatim in Qdrant.
    prefixed = [
        _prefix_context(sanitize_rag_content(c), client_name, doc_date) for c in chunks
    ]
    from app.services.embeddings import embed_texts

    ensure_collection()
    vectors = embed_texts(prefixed)
    upsert_to_qdrant(
        chunks=prefixed,
        vectors=vectors,
        client_id=client_id,
        doc_type=doc_type,
        doc_date=doc_date,
        topics=topics or [],
        client_name=client_name,
        document_id=document_id,
        filename=filename,
        source_type=source_type,
        ingested_at=ingested_at,
    )
