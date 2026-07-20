"""Authenticated lifetime-credit balance, ledger history, and contact requests."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.context import TenantContext
from app.deps import current_tenant
from app.services import credits

router = APIRouter()


def _contact_email() -> str:
    return os.environ.get("CREDIT_CONTACT_EMAIL", "").strip()


def _requests_enabled() -> bool:
    return os.environ.get("CREDIT_REQUEST_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )


class CreditContact(BaseModel):
    email: str
    request_enabled: bool


class CreditSummary(BaseModel):
    total_granted: int
    used: int
    remaining: int
    version: int
    costs: dict[str, int]
    contact: CreditContact


class HistoryItem(BaseModel):
    id: str
    created_at: str
    feature: str
    delta: int
    balance_after: int
    status: str
    description: str


class CreditHistory(BaseModel):
    entries: list[HistoryItem]
    total: int
    limit: int
    offset: int


class CreditRequestIn(BaseModel):
    message: Optional[str] = Field(default=None, max_length=2000)


class CreditRequestOut(BaseModel):
    id: str
    status: str
    message: str
    created_at: str
    contact_email: str


@router.get("", response_model=CreditSummary)
@router.get("/", response_model=CreditSummary, include_in_schema=False)
def summary(ctx: TenantContext = Depends(current_tenant)):
    result = credits.get_summary(ctx=ctx)
    email = _contact_email()
    return CreditSummary(
        **result,
        contact=CreditContact(
            email=email,
            request_enabled=_requests_enabled(),
        ),
    )


@router.get("/history", response_model=CreditHistory)
def history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: TenantContext = Depends(current_tenant),
):
    result = credits.get_history(limit=limit, offset=offset, ctx=ctx)
    return CreditHistory(**result, limit=limit, offset=offset)


@router.post("/requests", response_model=CreditRequestOut, status_code=202)
def request_credits(
    body: CreditRequestIn,
    ctx: TenantContext = Depends(current_tenant),
):
    if not _requests_enabled():
        raise HTTPException(status_code=403, detail="Credit requests are disabled.")
    result = credits.create_request(body.message, ctx=ctx)
    return CreditRequestOut(
        **result,
        message="Your request is pending review. We will contact you about additional credits.",
        contact_email=_contact_email(),
    )
