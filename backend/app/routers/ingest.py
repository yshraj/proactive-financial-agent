"""
Ingestion API: upload PDFs and Word (DOCX), duplicate check, then dual-path ingestion:
Path A = LLM extraction -> clients + alerts (Postgres); Path B = chunk + embed -> Qdrant client_memory.

Production posture:
- Originals persist to Supabase Storage under org-prefixed keys (Render disk is
  ephemeral); see services/storage.py.
- Async processing goes through the durable Postgres job queue (services/jobs)
  and is executed by the worker (app/worker.py) — restarts lose nothing.
- Duplicate detection is per-org (UNIQUE(org_id, content_hash)); another
  tenant's identical document is invisible.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from typing import Optional

import psycopg2
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.context import TenantContext
from app.db import get_cursor
from app.deps import current_tenant
from app.security import limiter
from app.services.cache import invalidate_client_ai_caches
from app.services import audit
from app.services import jobs
from app.services import llm_extractor
from app.services import note_templates
from app.services import storage
from app.services import vector_store
from app.services.safety import public_error_message, validate_docx_zip, validate_file_magic

logger = logging.getLogger("jarvis.ingest")

# Reject oversized uploads before buffering the whole file in memory (DoS guard).
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
_READ_CHUNK = 1024 * 1024

# Message when the ingested_documents table has not been created yet
TABLE_MISSING_MSG = (
    "The ingested_documents table is missing. Run database migrations "
    "(cd backend && alembic upgrade head), then retry."
)

router = APIRouter()

ALLOWED_EXTENSIONS = (".pdf", ".docx", ".md", ".txt")
_UPLOAD_TYPES_MSG = "Only PDF, Word (.docx), Markdown (.md), and text (.txt) files are accepted."


def _compute_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _allowed_file(filename: str) -> bool:
    if not filename:
        return False
    return filename.lower().endswith(ALLOWED_EXTENSIONS)


def _get_extension(filename: str) -> str:
    """Return the allowed extension for the filename; default .pdf."""
    lower = (filename or "").lower()
    for ext in ALLOWED_EXTENSIONS:
        if lower.endswith(ext):
            return ext
    return ".pdf"


def _sanitize_filename(name: str) -> str:
    """Keep only safe characters for display/storage; preserve the allowed extension."""
    base = os.path.basename(name)
    if not base:
        base = "document"
    name_no_ext, _, ext = base.rpartition(".")
    ext_lower = ext.lower() if ext else ""
    if f".{ext_lower}" not in ALLOWED_EXTENSIONS:
        ext_lower = "pdf"
    safe = re.sub(r"[^\w\-.]", "_", name_no_ext)[:100] or "document"
    return f"{safe}.{ext_lower}"


def _is_table_missing(err: Exception) -> bool:
    return isinstance(err, psycopg2.errors.UndefinedTable) and "ingested_documents" in str(err)


def _find_by_hash(content_hash: str, org_id: str) -> Optional[dict]:
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT id, filename, uploaded_at FROM ingested_documents"
                " WHERE content_hash = %s AND org_id = %s",
                (content_hash, org_id),
            )
            row = cur.fetchone()
        return dict(row) if row else None
    except psycopg2.Error as e:
        if _is_table_missing(e):
            raise HTTPException(status_code=503, detail=TABLE_MISSING_MSG) from e
        raise


def doc_type_for_ext(ext: str) -> tuple[str, str]:
    """Map a file extension to (display doc_type, qdrant source_type)."""
    if ext == ".pdf":
        return "PDF", "pdf"
    if ext == ".docx":
        return "Word", "docx"
    if ext == ".md":
        return "Markdown", "markdown"
    if ext == ".txt":
        return "Transcript", "transcript"
    return "Document", "document"


async def _read_validated_upload(request: Request, file: UploadFile) -> tuple[bytes, str]:
    """Shared upload validation: extension, size, magic bytes, zip bombs."""
    if not file.filename or not _allowed_file(file.filename):
        raise HTTPException(status_code=400, detail=_UPLOAD_TYPES_MSG)

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
            detail="File content does not match its extension.",
        )
    if ext == ".docx":
        ok, reason = validate_docx_zip(content)
        if not ok:
            raise HTTPException(status_code=400, detail=f"DOCX rejected: {reason}")
    return content, ext


def _store_document_row(
    *,
    org_id: str,
    file_id: str,
    display_filename: str,
    content_hash: str,
    file_path: str,
    file_size: int,
) -> dict:
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO ingested_documents (id, org_id, filename, content_hash, file_path, file_size_bytes)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, filename, content_hash, file_size_bytes, uploaded_at
                """,
                (file_id, org_id, display_filename, content_hash, file_path, file_size),
            )
            return cur.fetchone()
    except psycopg2.Error as e:
        if _is_table_missing(e):
            raise HTTPException(status_code=503, detail=TABLE_MISSING_MSG) from e
        raise


def run_dual_path_ingestion_from_storage(
    file_path_ref: str,
    display_filename: str,
    ext: str,
    document_id: str,
    ingested_at: Optional[str] = None,
) -> Optional[str]:
    """
    Path A: fetch stored bytes -> extract text -> LLM -> insert clients + alerts.
    Path B: chunk text -> embed -> upsert Qdrant with full metadata.
    Returns None on success, or an error message string on failure.
    Idempotent per document: re-running for the same document_id re-links rather
    than duplicating the ingested_documents row (client rows are re-created by
    retries only if the first attempt failed before insert committed).
    """
    try:
        content = storage.fetch_document(file_path_ref)
    except Exception as e:
        logger.exception("[ingest] Stored document fetch failed: %s", e)
        return public_error_message("ingest_storage", e)
    try:
        extracted = llm_extractor.extract_structured_from_bytes(content, ext, display_filename)
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
    from app.context import require_current_tenant

    org_id = require_current_tenant().org_id
    logger.info("[ingest] -------- ingestion start: document_id=%s, filename=%s --------", document_id, display_filename)
    client_data = extracted.get("client") or {}
    alerts_data = extracted.get("alerts") or []
    raw_text = extracted.get("raw_text") or ""

    full_name = (client_data.get("full_name") or "Unknown Client").strip() or "Unknown Client"
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
            # Idempotency: a retried job whose first attempt already inserted a
            # client for this document reuses it instead of duplicating. The
            # insert and the document link commit atomically.
            cur.execute(
                "SELECT client_id FROM ingested_documents WHERE id = %s AND org_id = %s",
                (document_id, org_id),
            )
            existing = cur.fetchone()
            client_id = str(existing["client_id"]) if existing and existing.get("client_id") else None
            if client_id is None:
                cur.execute(
                    """
                    INSERT INTO clients (org_id, full_name, retirement_target_age, risk_score, total_assets, cash_savings, last_review_date, raw_profile_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::date, %s::jsonb)
                    RETURNING id
                    """,
                    (org_id, full_name, retirement, risk, total_assets, cash_savings, last_review, raw_json),
                )
                row = cur.fetchone()
                client_id = str(row["id"])
                cur.execute(
                    "UPDATE ingested_documents SET client_id = %s WHERE id = %s AND org_id = %s",
                    (client_id, document_id, org_id),
                )
        logger.info(
            "[ingest] Postgres client ready: client_id=%s, risk_score=%s, review=%s",
            client_id,
            risk,
            last_review,
        )
    except psycopg2.Error as e:
        logger.exception("[ingest] Failed to insert client: %s", e)
        return f"Failed to insert client: {e!s}"

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
            (org_id, client_id, trigger_date, typ, priority, title, description, action_type, action_payload)
        )

    if alert_rows:
        try:
            with get_cursor(commit=True) as cur:
                # Idempotency: retried jobs must not duplicate this document's alerts.
                cur.execute(
                    "SELECT COUNT(*) AS n FROM alerts WHERE client_id = %s AND org_id = %s",
                    (client_id, org_id),
                )
                already = int((cur.fetchone() or {}).get("n") or 0)
                if already == 0:
                    cur.executemany(
                        """
                        INSERT INTO alerts (org_id, client_id, trigger_date, type, priority, title, description, action_type, action_payload)
                        VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        alert_rows,
                    )
                    logger.info("[ingest] Postgres alerts inserted: count=%s", len(alert_rows))
                else:
                    logger.info("[ingest] Alerts already present (%s); skipping insert (idempotent retry)", already)
        except psycopg2.Error as err:
            logger.warning("[ingest] Batch alert insert failed, falling back row-by-row: %s", err)
            for row in alert_rows:
                try:
                    with get_cursor(commit=True) as cur:
                        cur.execute(
                            """
                            INSERT INTO alerts (org_id, client_id, trigger_date, type, priority, title, description, action_type, action_payload)
                            VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s::jsonb)
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
    audit.record_event(
        action="document.processed",
        resource_type="document",
        resource_id=document_id,
        client_id=client_id,
        metadata={"alerts_created": len(alert_rows), "doc_type": ext.lstrip(".")},
        actor_type="system",
    )
    return None


class DocumentOut(BaseModel):
    id: str
    filename: str
    content_hash: str
    file_size_bytes: Optional[int]
    uploaded_at: str
    processing_error: Optional[str] = None  # Set if Path A/B (LLM or Qdrant) failed


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(ctx: TenantContext = Depends(current_tenant)):
    """Return this workspace's stored documents (PDF and DOCX) for the UI list."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, filename, content_hash, file_size_bytes, uploaded_at
                FROM ingested_documents
                WHERE org_id = %s
                ORDER BY uploaded_at DESC
                """,
                (ctx.org_id,),
            )
            rows = cur.fetchall()
    except psycopg2.Error as e:
        if _is_table_missing(e):
            raise HTTPException(status_code=503, detail=TABLE_MISSING_MSG) from e
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
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(current_tenant),
):
    """
    Upload a PDF or DOCX file. Reads content, computes SHA-256 hash, checks for duplicate.
    If duplicate: 409 with existing document info. If new: stores file and metadata, returns 201.
    """
    content, ext = await _read_validated_upload(request, file)

    content_hash = _compute_content_hash(content)
    existing = _find_by_hash(content_hash, ctx.org_id)
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

    file_id = str(uuid.uuid4())
    display_filename = _sanitize_filename(file.filename)
    try:
        file_path_ref = storage.save_document(ctx.org_id, file_id, ext, content)
    except Exception as e:
        raise HTTPException(status_code=502, detail=public_error_message("ingest_storage", e)) from e

    row = _store_document_row(
        org_id=ctx.org_id,
        file_id=file_id,
        display_filename=display_filename,
        content_hash=content_hash,
        file_path=file_path_ref,
        file_size=len(content),
    )
    audit.record_event(
        action="document.uploaded",
        resource_type="document",
        resource_id=file_id,
        metadata={"filename": display_filename, "bytes": len(content), "sync": True},
    )

    uploaded_at_iso = row["uploaded_at"].isoformat() if row.get("uploaded_at") else None
    processing_error = run_dual_path_ingestion_from_storage(
        file_path_ref, display_filename, ext,
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


@router.post("/upload-async", response_model=UploadJobResponse, status_code=202)
@limiter.limit("30/minute")
async def upload_document_async(
    request: Request,
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(current_tenant),
):
    """
    Upload a PDF/DOCX and process it via the durable job queue (Postgres-backed;
    executed by the worker process, survives restarts). Returns a job id
    immediately; poll GET /api/ingest/jobs/{job_id} for status.
    """
    content, ext = await _read_validated_upload(request, file)

    content_hash = _compute_content_hash(content)
    existing = _find_by_hash(content_hash, ctx.org_id)
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

    file_id = str(uuid.uuid4())
    display_filename = _sanitize_filename(file.filename)
    try:
        file_path_ref = storage.save_document(ctx.org_id, file_id, ext, content)
    except Exception as e:
        raise HTTPException(status_code=502, detail=public_error_message("ingest_storage", e)) from e

    row = _store_document_row(
        org_id=ctx.org_id,
        file_id=file_id,
        display_filename=display_filename,
        content_hash=content_hash,
        file_path=file_path_ref,
        file_size=len(content),
    )

    job = jobs.create(
        file_id,
        kind="upload",
        filename=display_filename,
        document_id=file_id,
        payload={
            "file_path": file_path_ref,
            "ext": ext,
            "ingested_at": row["uploaded_at"].isoformat() if row.get("uploaded_at") else None,
        },
    )
    audit.record_event(
        action="document.uploaded",
        resource_type="document",
        resource_id=file_id,
        metadata={"filename": display_filename, "bytes": len(content), "job_id": job["id"]},
    )
    return UploadJobResponse(job_id=job["id"], document_id=file_id, status=job["status"])


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, ctx: TenantContext = Depends(current_tenant)):
    """Status of a background ingestion job."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**{k: job.get(k) for k in JobStatusResponse.model_fields})


class NoteTemplateOut(BaseModel):
    id: str
    name: str
    section_count: int


class NoteTemplatesResponse(BaseModel):
    templates: list[NoteTemplateOut]


class RenderedTemplate(BaseModel):
    id: str
    name: str
    markdown: str


@router.get("/note-templates", response_model=NoteTemplatesResponse)
def get_note_templates():
    """List available adviser note templates."""
    return NoteTemplatesResponse(templates=[NoteTemplateOut(**t) for t in note_templates.list_templates()])


@router.get("/note-templates/{template_id}", response_model=RenderedTemplate)
def get_note_template(template_id: str):
    """Render a note template as a markdown skeleton."""
    try:
        markdown = note_templates.render_template(template_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Template not found.") from None
    return RenderedTemplate(
        id=template_id,
        name=note_templates.NOTE_TEMPLATES[template_id]["name"],
        markdown=markdown,
    )


class TranscriptRequest(BaseModel):
    text: str
    title: Optional[str] = None


# Transcripts can be long; cap to keep extraction bounded (matches extractor limit).
MAX_TRANSCRIPT_CHARS = 100_000
MIN_TRANSCRIPT_CHARS = 50


@router.post("/transcript", response_model=DocumentOut, status_code=201)
@limiter.limit("30/minute")
def ingest_transcript(
    request: Request, body: TranscriptRequest, ctx: TenantContext = Depends(current_tenant)
):
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
    existing = _find_by_hash(content_hash, ctx.org_id)
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

    row = _store_document_row(
        org_id=ctx.org_id,
        file_id=file_id,
        display_filename=display_filename,
        content_hash=content_hash,
        file_path=f"transcript:{file_id}",
        file_size=size_bytes,
    )
    audit.record_event(
        action="document.uploaded",
        resource_type="document",
        resource_id=file_id,
        metadata={"filename": display_filename, "bytes": size_bytes, "transcript": True},
    )

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
