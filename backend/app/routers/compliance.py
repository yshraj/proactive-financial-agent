"""
Compliance API: scan free-text adviser notes for vulnerability and Consumer
Duty signals. Deterministic (no LLM); the heavy lifting is in services/compliance.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.security import limiter
from app.services import audit
from app.services.compliance import scan_text
from app.services.posture import get_posture

router = APIRouter()

# Bound the input so a huge paste can't be used to exhaust memory.
MAX_SCAN_CHARS = 50_000


class ScanRequest(BaseModel):
    text: str


class Signal(BaseModel):
    category: Optional[str] = None
    outcome: Optional[str] = None
    phrase: str
    excerpt: str


class ScanSummary(BaseModel):
    vulnerability_count: int
    consumer_duty_count: int


class ScanResponse(BaseModel):
    vulnerability_signals: list[Signal]
    consumer_duty_flags: list[Signal]
    summary: ScanSummary


@router.post("/scan", response_model=ScanResponse)
@limiter.limit("30/minute")
def scan(request: Request, body: ScanRequest):
    """Flag vulnerability drivers (FG21/1) and Consumer Duty signals in notes."""
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Provide some text to scan.")
    result = scan_text(text[:MAX_SCAN_CHARS])
    return ScanResponse(**result)


class AuditEntry(BaseModel):
    id: int
    kind: str
    timestamp: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    model: Optional[str] = None
    preview: str
    ai_generated: bool
    reviewed: bool = False
    reviewed_at: Optional[str] = None


class AuditResponse(BaseModel):
    entries: list[AuditEntry]


@router.get("/audit", response_model=AuditResponse)
def get_audit(limit: int = Query(50, ge=1, le=500, description="Max entries to return")):
    """Recent AI-output audit trail (newest first) for accountability."""
    return AuditResponse(entries=[AuditEntry(**e) for e in audit.recent(limit)])


class PostureResponse(BaseModel):
    trains_on_client_data: bool
    data_residency: str
    data_retention_days: Optional[int] = None
    llm_provider: str
    encryption_at_rest: bool
    encryption_in_transit: bool
    auth_required: bool


@router.get("/posture", response_model=PostureResponse)
def get_compliance_posture():
    """Report the deployment's configured data-handling & AI posture."""
    return PostureResponse(**get_posture(os.environ))


@router.post("/audit/{entry_id}/approve", response_model=AuditEntry)
@limiter.limit("60/minute")
def approve_audit_entry(request: Request, entry_id: int):
    """Mark an AI output as human-reviewed — the Consumer-Duty approval gate."""
    updated = audit.approve(entry_id, datetime.now().isoformat())
    if updated is None:
        raise HTTPException(status_code=404, detail="Audit entry not found.")
    return AuditEntry(**updated)
