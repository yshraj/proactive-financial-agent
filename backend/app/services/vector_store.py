"""
Path B: Chunk text, add context, embed with OpenAI, upsert to Qdrant client_memory.
Payload includes content + metadata for filtered vector search:
  - content, client_id, client_name, doc_type, date, topics (architecture)
  - document_id, filename, source_type, ingested_at (for metadata filters)
"""
import logging
import os
import uuid

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


def _prefix_context(chunk: str, client_name: str, doc_date: str | None) -> str:
    """Prepend 'Client Name: X | Date: Y' to chunk for better retrieval (architecture)."""
    date_part = f" | Date: {doc_date}" if doc_date else ""
    return f"Client Name: {client_name}{date_part}\n\n{chunk}"


def get_embeddings_openai(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Batch embed texts with OpenAI. Returns list of vectors."""
    from app.services.clients import get_openai_client
    model = model or os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    client = get_openai_client()
    r = client.embeddings.create(input=texts, model=model)
    return [d.embedding for d in r.data]


def upsert_to_qdrant(
    chunks: list[str],
    vectors: list[list[float]],
    client_id: str,
    doc_type: str = "Document",
    doc_date: str | None = None,
    topics: list[str] | None = None,
    *,
    client_name: str | None = None,
    document_id: str | None = None,
    filename: str | None = None,
    source_type: str | None = None,
    ingested_at: str | None = None,
    collection: str = QDRANT_COLLECTION,
) -> None:
    """
    Upsert chunk vectors into Qdrant with full metadata for filtered search.
    Filterable payload fields: client_id, client_name, doc_type, date, topics,
    document_id, filename, source_type, ingested_at.
    """
    from qdrant_client.models import PointStruct

    from app.services.clients import get_qdrant_client

    client = get_qdrant_client()
    topics = topics or []
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vec,
            payload={
                "content": content,
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


def index_document_text(
    raw_text: str,
    client_id: str,
    client_name: str,
    doc_type: str = "Document",
    doc_date: str | None = None,
    *,
    document_id: str | None = None,
    filename: str | None = None,
    source_type: str | None = None,
    ingested_at: str | None = None,
    topics: list[str] | None = None,
) -> None:
    """
    Full Path B: chunk text, add context prefix, embed, upsert to Qdrant with metadata.
    All metadata is stored in payload for filtered vector search (client_id, doc_type, date,
    document_id, filename, source_type, ingested_at, topics).
    """
    if not raw_text or not raw_text.strip():
        logger.info("[ingest] Vector index skipped: no text")
        return
    chunks = chunk_text(raw_text)
    if not chunks:
        logger.info("[ingest] Vector index skipped: no chunks")
        return
    logger.info("[ingest] Vector index: %d chunks for client_name=%s, doc_type=%s", len(chunks), client_name, doc_type)
    prefixed = [_prefix_context(c, client_name, doc_date) for c in chunks]
    vectors = get_embeddings_openai(prefixed)
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
