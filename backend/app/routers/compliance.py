"""
Compliance API: scan free-text adviser notes for vulnerability and Consumer
Duty signals, plus the AI audit surfaces (review register + immutable events).
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app.context import TenantContext
from app.deps import current_tenant
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
def scan(
    request: Request,
    response: Response,  # slowapi injects X-RateLimit headers (headers_enabled)
    body: ScanRequest,
    ctx: TenantContext = Depends(current_tenant),
):
    """Flag vulnerability drivers (FG21/1) and Consumer Duty signals in notes."""
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Provide some text to scan.")
    result = scan_text(text[:MAX_SCAN_CHARS])
    # Record signal counts only — never the scanned note text (PII).
    audit.record_event(
        action="compliance.scan.run",
        resource_type="scan",
        metadata={
            "chars": len(text[:MAX_SCAN_CHARS]),
            "vulnerability_count": result["summary"]["vulnerability_count"],
            "consumer_duty_count": result["summary"]["consumer_duty_count"],
        },
    )
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
def get_audit(
    limit: int = Query(50, ge=1, le=500, description="Max entries to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    ctx: TenantContext = Depends(current_tenant),
):
    """Recent AI-output audit trail (newest first) for accountability."""
    return AuditResponse(entries=[AuditEntry(**e) for e in audit.recent(limit, offset=offset)])


class AuditEventOut(BaseModel):
    id: int
    actor_user_id: Optional[str] = None
    actor_type: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    client_id: Optional[str] = None
    request_id: Optional[str] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: str


class AuditEventsResponse(BaseModel):
    events: list[AuditEventOut]


@router.get("/audit/events", response_model=AuditEventsResponse)
def get_audit_events(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None, description="Filter by action, e.g. client.updated"),
    client_id: Optional[str] = Query(None, description="Filter by client"),
    ctx: TenantContext = Depends(current_tenant),
):
    """The immutable event log (who/what/when/where), org-scoped and paginated."""
    rows = audit.events(limit, offset=offset, action=action, client_id=client_id)
    return AuditEventsResponse(events=[AuditEventOut(**r) for r in rows])


class PostureResponse(BaseModel):
    trains_on_client_data: bool
    data_residency: str
    data_retention_days: Optional[int] = None
    llm_provider: str
    encryption_at_rest: bool
    encryption_in_transit: bool
    auth_required: bool
    auth_mode: str
    durable_audit: bool


@router.get("/posture", response_model=PostureResponse)
def get_compliance_posture(ctx: TenantContext = Depends(current_tenant)):
    """Report the deployment's configured data-handling & AI posture."""
    return PostureResponse(**get_posture(os.environ))


@router.post("/audit/{entry_id}/approve", response_model=AuditEntry)
@limiter.limit("60/minute")
def approve_audit_entry(
    request: Request,
    response: Response,  # slowapi injects X-RateLimit headers (headers_enabled)
    entry_id: int,
    ctx: TenantContext = Depends(current_tenant),
):
    """Mark an AI output as human-reviewed — the Consumer-Duty approval gate."""
    updated = audit.approve(entry_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Audit entry not found.")
    return AuditEntry(**updated)
