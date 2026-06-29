"""
Compliance API: scan free-text adviser notes for vulnerability and Consumer
Duty signals. Deterministic (no LLM); the heavy lifting is in services/compliance.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.security import limiter
from app.services.compliance import scan_text

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
