"""
Ingestion API: upload PDFs and Word (DOCX), duplicate check, then dual-path ingestion:
Path A = LLM extraction -> clients + alerts (Postgres); Path B = chunk + embed -> Qdrant client_memory.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import psycopg2
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.db import get_cursor
from app.security import limiter
from app.services.config import ADVISER_ID
from app.services.cache import invalidate_client_ai_caches
from app.services import jobs
from app.services import llm_extractor
from app.services import vector_store
from app.services.safety import public_error_message, validate_file_magic

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


def doc_type_for_ext(ext: str) -> tuple[str, str]:
    """Map a file extension to (display doc_type, qdrant source_type)."""
    if ext == ".pdf":
        return "PDF", "pdf"
    if ext == ".docx":
        return "Word", "docx"
    if ext == ".txt":
        return "Transcript", "transcript"
    return "Document", "document"


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
    try:
        extracted = llm_extractor.extract_structured(file_path)
    except Exception as e:
        logger.exception("[ingest] Extraction failed: %s", e)
        return public_error_message("ingest_extraction", e)
    return _persist_extraction(extracted, display_filename, ext, document_id, ingested_at)


def _persist_extraction(
    extracted: dict,
    display_filename: str,
    ext: str,
    document_id: str,
    ingested_at: Optional[str] = None,
) -> Optional[str]:
    """
    Write an extracted {client, alerts, raw_text} payload to Postgres + Qdrant.
    Shared by file upload and transcript ingestion. Returns None on success or an
    error message string on failure.
    """
    logger.info("[ingest] -------- ingestion start: document_id=%s, filename=%s --------", document_id, display_filename)
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

    # Link this document to the client it produced so Client 360 can count it.
    # Degrade gracefully if migration 002 hasn't been applied yet.
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE ingested_documents SET client_id = %s WHERE id = %s",
                (client_id, document_id),
            )
    except psycopg2.errors.UndefinedColumn:
        logger.info(
            "[ingest] ingested_documents.client_id missing; skipping link (run migration 002)"
        )
    except psycopg2.Error as e:
        logger.warning("[ingest] Failed to link document to client: %s", e)

    alert_rows: list[tuple] = []
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
        alert_rows.append(
            (client_id, trigger_date, typ, priority, title, description, action_type, action_payload)
        )

    if alert_rows:
        try:
            with get_cursor(commit=True) as cur:
                cur.executemany(
                    """
                    INSERT INTO alerts (client_id, trigger_date, type, priority, title, description, action_type, action_payload)
                    VALUES (%s, %s::date, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    alert_rows,
                )
            logger.info("[ingest] Postgres alerts inserted: count=%s", len(alert_rows))
        except psycopg2.Error as err:
            logger.warning("[ingest] Batch alert insert failed, falling back row-by-row: %s", err)
            for row in alert_rows:
                try:
                    with get_cursor(commit=True) as cur:
                        cur.execute(
                            """
                            INSERT INTO alerts (client_id, trigger_date, type, priority, title, description, action_type, action_payload)
                            VALUES (%s, %s::date, %s, %s, %s, %s, %s, %s::jsonb)
                            """,
                            row,
                        )
                except psycopg2.Error as row_err:
                    logger.warning("[ingest] Alert insert skipped (bad row): %s", row_err)

    try:
        doc_type, source_type = doc_type_for_ext(ext)
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

    invalidate_client_ai_caches(client_id)
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

    ext = _get_extension(file.filename)
    if not validate_file_magic(content, ext):
        raise HTTPException(
            status_code=400,
            detail="File content does not match its extension. Only valid PDF and DOCX files are accepted.",
        )

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


class UploadJobResponse(BaseModel):
    job_id: str
    document_id: str
    status: str


class JobStatusResponse(BaseModel):
    id: str
    kind: str
    filename: Optional[str] = None
    status: str
    progress: int
    message: str
    document_id: Optional[str] = None
    error: Optional[str] = None


def _process_upload_job(
    job_id: str, file_path: Path, display_filename: str, ext: str, document_id: str, ingested_at: Optional[str]
) -> None:
    """Background worker: run dual-path ingestion and record progress on the job."""
    jobs.update(job_id, status=jobs.PROCESSING, progress=40, message="Extracting and indexing…")
    try:
        err = _run_dual_path_ingestion(file_path, display_filename, ext, document_id, ingested_at)
    except Exception as e:  # defensive: never let a background error escape silently
        logger.exception("[ingest] Async job %s failed: %s", job_id, e)
        jobs.update(job_id, status=jobs.ERROR, progress=100, message="Failed", error=str(e))
        return
    if err:
        jobs.update(job_id, status=jobs.ERROR, progress=100, message="Completed with issues",
                    error=err, document_id=document_id)
    else:
        jobs.update(job_id, status=jobs.DONE, progress=100, message="Done", document_id=document_id)


@router.post("/upload-async", response_model=UploadJobResponse, status_code=202)
@limiter.limit("30/minute")
async def upload_document_async(
    request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)
):
    """
    Upload a PDF/DOCX and process it in the background (FastAPI BackgroundTasks,
    in-process — no external worker). Returns a job id immediately; poll
    GET /api/ingest/jobs/{job_id} for status. The synchronous /upload is unchanged.
    """
    if not file.filename or not _allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="Only PDF and Word (.docx) files are accepted.")

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")

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

    ext = _get_extension(file.filename)
    if not validate_file_magic(content, ext):
        raise HTTPException(status_code=400, detail="File content does not match its extension. Only valid PDF and DOCX files are accepted.")

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
            },
        )

    _ensure_uploads_dir()
    file_id = str(uuid.uuid4())
    stored_name = f"{file_id}{ext}"
    file_path = UPLOADS_DIR / stored_name
    with open(file_path, "wb") as f:
        f.write(content)
    display_filename = _sanitize_filename(file.filename)

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO ingested_documents (id, filename, content_hash, file_path, file_size_bytes)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, uploaded_at
                """,
                (file_id, display_filename, content_hash, f"uploads/{stored_name}", len(content)),
            )
            row = cur.fetchone()
    except psycopg2.Error as e:
        if _is_table_missing(e):
            raise HTTPException(status_code=503, detail=TABLE_MISSING_MSG)
        raise

    job = jobs.create(file_id, kind="upload", filename=display_filename)
    ingested_at = row["uploaded_at"].isoformat() if row.get("uploaded_at") else None
    background_tasks.add_task(
        _process_upload_job, file_id, file_path, display_filename, ext, file_id, ingested_at
    )
    return UploadJobResponse(job_id=job["id"], document_id=file_id, status=job["status"])


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str):
    """Status of a background ingestion job."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job)


class TranscriptRequest(BaseModel):
    text: str
    title: Optional[str] = None


# Transcripts can be long; cap to keep extraction bounded (matches extractor limit).
MAX_TRANSCRIPT_CHARS = 100_000
MIN_TRANSCRIPT_CHARS = 50


@router.post("/transcript", response_model=DocumentOut, status_code=201)
@limiter.limit("30/minute")
def ingest_transcript(request: Request, body: TranscriptRequest):
    """
    Ingest a pasted meeting transcript: run the same dual-path pipeline as file
    upload (LLM extraction -> Postgres clients/alerts; chunk+embed -> Qdrant),
    without requiring a file. Duplicate transcripts are detected by content hash.
    """
    text = (body.text or "").strip()
    if len(text) < MIN_TRANSCRIPT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Transcript is too short to process (minimum {MIN_TRANSCRIPT_CHARS} characters).",
        )
    text = text[:MAX_TRANSCRIPT_CHARS]

    content_hash = _compute_content_hash(text.encode("utf-8"))
    existing = _find_by_hash(content_hash)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE",
                "message": "This transcript has the same content as one already in the system.",
                "existing_id": str(existing["id"]),
                "existing_filename": existing["filename"],
            },
        )

    file_id = str(uuid.uuid4())
    title = (body.title or "").strip()
    safe_title = re.sub(r"[^\w\-]", "_", title)[:80] if title else f"transcript-{file_id[:8]}"
    display_filename = f"{safe_title}.txt"
    size_bytes = len(text.encode("utf-8"))

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO ingested_documents (id, filename, content_hash, file_path, file_size_bytes)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, filename, content_hash, file_size_bytes, uploaded_at
                """,
                (file_id, display_filename, content_hash, f"transcript:{file_id}", size_bytes),
            )
            row = cur.fetchone()
    except psycopg2.Error as e:
        if _is_table_missing(e):
            raise HTTPException(status_code=503, detail=TABLE_MISSING_MSG)
        raise

    uploaded_at_iso = row["uploaded_at"].isoformat() if row.get("uploaded_at") else None
    try:
        extracted = llm_extractor.extract_structured_from_text(text)
    except Exception as e:
        logger.exception("[ingest] Transcript extraction failed: %s", e)
        return DocumentOut(
            id=str(row["id"]),
            filename=row["filename"],
            content_hash=row["content_hash"],
            file_size_bytes=row["file_size_bytes"],
            uploaded_at=uploaded_at_iso or "",
            processing_error=public_error_message("ingest_extraction", e),
        )

    processing_error = _persist_extraction(
        extracted, display_filename, ".txt", document_id=file_id, ingested_at=uploaded_at_iso
    )
    return DocumentOut(
        id=str(row["id"]),
        filename=row["filename"],
        content_hash=row["content_hash"],
        file_size_bytes=row["file_size_bytes"],
        uploaded_at=uploaded_at_iso or "",
        processing_error=processing_error,
    )
