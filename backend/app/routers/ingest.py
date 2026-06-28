"""
Ingestion API: upload PDFs and Word (DOCX), duplicate check, then dual-path ingestion:
Path A = LLM extraction -> clients + alerts (Postgres); Path B = chunk + embed -> Qdrant client_memory.
"""
import hashlib
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import psycopg2
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.db import get_cursor
from app.security import limiter
from app.services.config import ADVISER_ID
from app.services import llm_extractor
from app.services import vector_store

logger = logging.getLogger("jarvis.ingest")

# Reject oversized uploads before buffering the whole file in memory (DoS guard).
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
_READ_CHUNK = 1024 * 1024

# Message when the ingested_documents table has not been created yet
TABLE_MISSING_MSG = (
    "The ingested_documents table is missing. In Supabase Dashboard go to SQL Editor, "
    "open backend/migrations/001_ingested_documents.sql, run it, then retry."
)

router = APIRouter()

ALLOWED_EXTENSIONS = (".pdf", ".docx")

# Directory to store uploaded files (relative to backend root)
BACKEND_ROOT = Path(__file__).resolve().parents[2]
UPLOADS_DIR = BACKEND_ROOT / "uploads"


def _ensure_uploads_dir():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _compute_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _allowed_file(filename: str) -> bool:
    if not filename:
        return False
    return filename.lower().endswith(ALLOWED_EXTENSIONS)


def _get_extension(filename: str) -> str:
    """Return .pdf or .docx based on filename; default .pdf."""
    if not filename:
        return ".pdf"
    lower = filename.lower()
    if lower.endswith(".docx"):
        return ".docx"
    return ".pdf"


def _sanitize_filename(name: str) -> str:
    """Keep only safe characters for display/storage; preserve .pdf or .docx."""
    base = os.path.basename(name)
    if not base:
        base = "document"
    name_no_ext, _, ext = base.rpartition(".")
    ext_lower = ext.lower() if ext else ""
    if ext_lower not in ("pdf", "docx"):
        ext_lower = "pdf"
    safe = re.sub(r"[^\w\-.]", "_", name_no_ext)[:100] or "document"
    return f"{safe}.{ext_lower}"


def _is_table_missing(err: Exception) -> bool:
    return isinstance(err, psycopg2.errors.UndefinedTable) and "ingested_documents" in str(err)


def _find_by_hash(content_hash: str) -> Optional[dict]:
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT id, filename, uploaded_at FROM ingested_documents WHERE content_hash = %s",
                (content_hash,),
            )
            row = cur.fetchone()
        return dict(row) if row else None
    except psycopg2.Error as e:
        if _is_table_missing(e):
            raise HTTPException(status_code=503, detail=TABLE_MISSING_MSG)
        raise


def _run_dual_path_ingestion(
    file_path: Path,
    display_filename: str,
    ext: str,
    document_id: str,
    ingested_at: Optional[str] = None,
) -> Optional[str]:
    """
    Path A: Extract text -> LLM -> insert clients + alerts.
    Path B: Chunk text -> embed -> upsert Qdrant client_memory with full metadata for filtered search.
    Returns None on success, or an error message string on failure.
    """
    logger.info("[ingest] -------- ingestion start: document_id=%s, filename=%s --------", document_id, display_filename)
    try:
        extracted = llm_extractor.extract_structured(file_path)
    except Exception as e:
        logger.exception("[ingest] Extraction failed: %s", e)
        return f"Extraction failed: {e!s}"

    client_data = extracted.get("client") or {}
    alerts_data = extracted.get("alerts") or []
    raw_text = extracted.get("raw_text") or ""

    full_name = (client_data.get("full_name") or "Unknown Client").strip() or "Unknown Client"
    adviser_id_val = ADVISER_ID if ADVISER_ID else None
    retirement = client_data.get("retirement_target_age")
    risk = client_data.get("risk_score")
    if risk is not None and (not isinstance(risk, (int, float)) or risk < 1 or risk > 10):
        try:
            risk = max(1, min(10, int(risk)))
        except (TypeError, ValueError):
            risk = None
    total_assets = client_data.get("total_assets")
    cash_savings = client_data.get("cash_savings")
    last_review = client_data.get("last_review_date")
    raw_json = client_data.get("raw_profile_json")
    if isinstance(raw_json, dict):
        raw_json = json.dumps(raw_json)
    elif raw_json is not None and not isinstance(raw_json, str):
        raw_json = json.dumps(raw_json)

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO clients (full_name, adviser_id, retirement_target_age, risk_score, total_assets, cash_savings, last_review_date, raw_profile_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s::date, %s::jsonb)
                RETURNING id
                """,
                (full_name, adviser_id_val, retirement, risk, total_assets, cash_savings, last_review, raw_json),
            )
            row = cur.fetchone()
            client_id = str(row["id"])
        logger.info(
            "[ingest] Postgres client inserted: client_id=%s, full_name=%s, risk_score=%s, total_assets=%s, last_review=%s",
            client_id,
            full_name,
            risk,
            total_assets,
            last_review,
        )
    except psycopg2.Error as e:
        logger.exception("[ingest] Failed to insert client: %s", e)
        return f"Failed to insert client: {e!s}"

    for a in alerts_data:
        trigger_date = a.get("trigger_date")
        if not trigger_date:
            continue
        typ = (a.get("type") or "COMPLIANCE")[:50]
        priority = (a.get("priority") or "MEDIUM")[:20]
        title = (a.get("title") or "")[: 2**16]
        description = (a.get("description") or "")[: 2**16]
        action_type = (a.get("action_type") or "")[:50]
        action_payload = a.get("action_payload")
        if isinstance(action_payload, dict):
            action_payload = json.dumps(action_payload)
        elif action_payload is not None and not isinstance(action_payload, str):
            action_payload = json.dumps(action_payload)
        try:
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    INSERT INTO alerts (client_id, trigger_date, type, priority, title, description, action_type, action_payload)
                    VALUES (%s, %s::date, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (client_id, trigger_date, typ, priority, title, description, action_type, action_payload),
                )
            logger.info(
                "[ingest] Postgres alert inserted: trigger_date=%s, type=%s, priority=%s, title=%s",
                trigger_date,
                typ,
                priority,
                (title or "")[:60],
            )
        except psycopg2.Error as err:
            logger.warning("[ingest] Alert insert skipped (bad row): %s", err)

    try:
        doc_type = "PDF" if ext == ".pdf" else "Word"
        source_type = "pdf" if ext == ".pdf" else "docx"
        vector_store.index_document_text(
            raw_text=raw_text,
            client_id=client_id,
            client_name=full_name,
            doc_type=doc_type,
            doc_date=last_review,
            document_id=document_id,
            filename=display_filename,
            source_type=source_type,
            ingested_at=ingested_at,
        )
        logger.info("[ingest] -------- ingestion done: document_id=%s, client_id=%s --------", document_id, client_id)
    except Exception as e:
        logger.exception("[ingest] Qdrant indexing failed: %s", e)
        return f"Qdrant indexing failed: {e!s}"

    return None


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_hash: str
    file_size_bytes: Optional[int]
    uploaded_at: str
    processing_error: Optional[str] = None  # Set if Path A/B (LLM or Qdrant) failed


@router.get("/documents", response_model=list[DocumentOut])
def list_documents():
    """Return all stored documents (PDF and DOCX) for the UI list."""
    _ensure_uploads_dir()
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, filename, content_hash, file_size_bytes, uploaded_at
                FROM ingested_documents
                ORDER BY uploaded_at DESC
                """
            )
            rows = cur.fetchall()
    except psycopg2.Error as e:
        if _is_table_missing(e):
            raise HTTPException(status_code=503, detail=TABLE_MISSING_MSG)
        raise
    return [
        DocumentOut(
            id=str(r["id"]),
            filename=r["filename"],
            content_hash=r["content_hash"],
            file_size_bytes=r["file_size_bytes"],
            uploaded_at=r["uploaded_at"].isoformat() if r["uploaded_at"] else "",
        )
        for r in rows
    ]


@router.post("/upload", response_model=DocumentOut, status_code=201)
@limiter.limit("30/minute")
async def upload_document(request: Request, file: UploadFile = File(...)):
    """
    Upload a PDF or DOCX file. Reads content, computes SHA-256 hash, checks for duplicate.
    If duplicate: 409 with existing document info. If new: stores file and metadata, returns 201.
    """
    if not file.filename or not _allowed_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Only PDF and Word (.docx) files are accepted.",
        )

    # Fast-path reject using Content-Length when present.
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")

    # Read in bounded chunks so a huge upload can't exhaust memory.
    buffer = bytearray()
    while True:
        chunk = await file.read(_READ_CHUNK)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
    content = bytes(buffer)
    if not content:
        raise HTTPException(status_code=400, detail="File is empty.")

    content_hash = _compute_content_hash(content)
    existing = _find_by_hash(content_hash)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE",
                "message": "This file has the same content as one already in the system.",
                "existing_id": str(existing["id"]),
                "existing_filename": existing["filename"],
                "existing_uploaded_at": existing["uploaded_at"].isoformat() if existing.get("uploaded_at") else None,
            },
        )

    _ensure_uploads_dir()
    ext = _get_extension(file.filename)
    file_id = str(uuid.uuid4())
    stored_name = f"{file_id}{ext}"
    file_path = UPLOADS_DIR / stored_name
    with open(file_path, "wb") as f:
        f.write(content)
    file_size = len(content)
    display_filename = _sanitize_filename(file.filename)
    # Store relative path for portability
    relative_path = f"uploads/{stored_name}"

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO ingested_documents (id, filename, content_hash, file_path, file_size_bytes)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, filename, content_hash, file_size_bytes, uploaded_at
                """,
                (file_id, display_filename, content_hash, relative_path, file_size),
            )
            row = cur.fetchone()
    except psycopg2.Error as e:
        if _is_table_missing(e):
            raise HTTPException(status_code=503, detail=TABLE_MISSING_MSG)
        raise

    uploaded_at_iso = row["uploaded_at"].isoformat() if row.get("uploaded_at") else None
    processing_error = _run_dual_path_ingestion(
        file_path, display_filename, ext,
        document_id=file_id,
        ingested_at=uploaded_at_iso,
    )

    return DocumentOut(
        id=str(row["id"]),
        filename=row["filename"],
        content_hash=row["content_hash"],
        file_size_bytes=row["file_size_bytes"],
        uploaded_at=row["uploaded_at"].isoformat() if row["uploaded_at"] else "",
        processing_error=processing_error,
    )
