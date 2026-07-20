"""Lifetime AI credits with atomic, tenant-scoped reservations.

All balance mutations happen in PostgreSQL SECURITY DEFINER functions. This
module is intentionally a thin typed boundary around those functions so API
and worker callers share the same idempotency and error semantics.
"""
from __future__ import annotations

import functools
import inspect
import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

import psycopg2

from app.context import TenantContext, require_current_tenant
from app.db import get_cursor


class CreditFeature(str, Enum):
    CHAT = "chat"
    REPORT = "report"
    IMAGE = "image"
    PDF_ANALYSIS = "pdf_analysis"
    DEEP_RESEARCH = "deep_research"
    DRAFT_EMAIL = "draft_email"
    DIGEST = "digest"
    REVIEW_NOTE = "review_note"
    CLIENT_SUMMARY = "client_summary"
    TRANSCRIPT_ANALYSIS = "transcript_analysis"


FEATURE_COSTS: dict[CreditFeature, int] = {
    CreditFeature.CHAT: 1,
    CreditFeature.REPORT: 5,
    CreditFeature.IMAGE: 3,
    CreditFeature.PDF_ANALYSIS: 2,
    CreditFeature.DEEP_RESEARCH: 10,
    CreditFeature.DRAFT_EMAIL: 2,
    CreditFeature.DIGEST: 2,
    CreditFeature.REVIEW_NOTE: 3,
    CreditFeature.CLIENT_SUMMARY: 1,
    CreditFeature.TRANSCRIPT_ANALYSIS: 2,
}


def default_lifetime_credits() -> int:
    try:
        return max(0, int(os.environ.get("DEFAULT_LIFETIME_CREDITS", "200")))
    except ValueError:
        return 200


def principal_for(ctx: TenantContext) -> str:
    """User account when authenticated; one shared org account otherwise."""
    return str(ctx.user_id) if ctx.user_id else f"org:{ctx.org_id}"


class CreditError(Exception):
    pass


class CreditBalanceUnavailable(CreditError):
    pass


class InsufficientCredits(CreditError):
    def __init__(self, *, required: int, remaining: int, feature: str):
        self.required = required
        self.remaining = remaining
        self.feature = feature
        super().__init__(f"{feature} requires {required} credits; {remaining} remain")


class DuplicateCreditAction(CreditError):
    def __init__(self, *, feature: str, status: str):
        self.feature = feature
        self.status = status
        super().__init__(f"Credit action {feature!r} was already {status}")


@dataclass(frozen=True)
class Reservation:
    id: str
    feature: CreditFeature
    cost: int
    status: str
    remaining: int
    version: int


def _ctx(ctx: Optional[TenantContext]) -> TenantContext:
    return ctx or require_current_tenant()


def _database_error(exc: psycopg2.Error) -> CreditError:
    if getattr(exc, "pgcode", None) == "P0001" and "insufficient_credits" in str(exc):
        detail = getattr(getattr(exc, "diag", None), "message_detail", None)
        try:
            payload = json.loads(detail or "{}")
        except (TypeError, json.JSONDecodeError):
            payload = {}
        return InsufficientCredits(
            required=int(payload.get("required") or 0),
            remaining=int(payload.get("remaining") or 0),
            feature=str(payload.get("feature") or "unknown"),
        )
    return CreditBalanceUnavailable("Credit balance is temporarily unavailable")


def reserve(
    feature: CreditFeature,
    idempotency_key: str,
    *,
    ctx: Optional[TenantContext] = None,
) -> Reservation:
    tenant = _ctx(ctx)
    cost = FEATURE_COSTS[feature]
    key = str(idempotency_key or "").strip()[:250]
    if not key:
        raise ValueError("idempotency_key is required")
    try:
        with get_cursor(commit=True, ctx=tenant) as cur:
            cur.execute(
                """
                SELECT * FROM reserve_credits(
                    %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    tenant.org_id,
                    principal_for(tenant),
                    tenant.user_id,
                    feature.value,
                    cost,
                    key,
                    default_lifetime_credits(),
                ),
            )
            row = cur.fetchone()
    except psycopg2.Error as exc:
        raise _database_error(exc) from exc
    if not row:
        raise CreditBalanceUnavailable("Credit reservation returned no result")
    if bool(row.get("is_replay")):
        raise DuplicateCreditAction(
            feature=feature.value,
            status=str(row["reservation_status"]),
        )
    return Reservation(
        id=str(row["reservation_id"]),
        feature=feature,
        cost=int(row["required"]),
        status=row["reservation_status"],
        remaining=int(row["remaining"]),
        version=int(row["account_version"]),
    )


def commit(reservation_id: str, *, ctx: Optional[TenantContext] = None) -> str:
    tenant = _ctx(ctx)
    try:
        with get_cursor(commit=True, ctx=tenant) as cur:
            cur.execute(
                "SELECT (commit_credit_reservation(%s)).status AS status",
                (reservation_id,),
            )
            row = cur.fetchone()
    except psycopg2.Error as exc:
        raise _database_error(exc) from exc
    if not row:
        raise CreditBalanceUnavailable("Credit commit returned no result")
    return str(row["status"])


def release(reservation_id: str, *, ctx: Optional[TenantContext] = None) -> str:
    tenant = _ctx(ctx)
    try:
        with get_cursor(commit=True, ctx=tenant) as cur:
            cur.execute(
                "SELECT (release_credit_reservation(%s)).status AS status",
                (reservation_id,),
            )
            row = cur.fetchone()
    except psycopg2.Error as exc:
        raise _database_error(exc) from exc
    if not row:
        raise CreditBalanceUnavailable("Credit release returned no result")
    return str(row["status"])


def get_summary(*, ctx: Optional[TenantContext] = None) -> dict[str, Any]:
    tenant = _ctx(ctx)
    try:
        with get_cursor(commit=True, ctx=tenant) as cur:
            cur.execute(
                "SELECT * FROM credit_get_or_create_account(%s, %s, %s, %s)",
                (
                    tenant.org_id,
                    principal_for(tenant),
                    tenant.user_id,
                    default_lifetime_credits(),
                ),
            )
            account = cur.fetchone()
            if not account:
                raise CreditBalanceUnavailable(
                    "Credit account lookup returned no result"
                )
            cur.execute(
                """
                SELECT COALESCE(sum(cost), 0) AS reserved
                FROM credit_reservations
                WHERE account_id = %s AND status = 'reserved'
                """,
                (account["id"],),
            )
            reserved = int((cur.fetchone() or {}).get("reserved") or 0)
    except psycopg2.Error as exc:
        raise _database_error(exc) from exc
    return {
        "total_granted": int(account["total_granted"]),
        "used": int(account["used"]),
        "remaining": max(
            int(account["total_granted"]) - int(account["used"]) - reserved, 0
        ),
        "version": int(account["version"]),
        "costs": {feature.value: cost for feature, cost in FEATURE_COSTS.items()},
    }


def get_history(
    *, limit: int = 50, offset: int = 0, ctx: Optional[TenantContext] = None
) -> dict[str, Any]:
    tenant = _ctx(ctx)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    try:
        with get_cursor(commit=True, ctx=tenant) as cur:
            cur.execute(
                "SELECT * FROM credit_get_or_create_account(%s, %s, %s, %s)",
                (
                    tenant.org_id,
                    principal_for(tenant),
                    tenant.user_id,
                    default_lifetime_credits(),
                ),
            )
            account = cur.fetchone()
            if not account:
                raise CreditBalanceUnavailable(
                    "Credit account lookup returned no result"
                )
            cur.execute(
                """
                SELECT id, entry_type, amount, feature, balance_after, status,
                       description, created_at, COUNT(*) OVER() AS total_count
                FROM credit_ledger
                WHERE account_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (account["id"], limit, offset),
            )
            rows = cur.fetchall()
    except psycopg2.Error as exc:
        raise _database_error(exc) from exc
    entries = [
        {
            "id": str(row["id"]),
            "created_at": row["created_at"].isoformat(),
            "feature": row.get("feature")
            or (
                "initial_allocation"
                if row["entry_type"] == "grant"
                and row["description"] == "Initial lifetime credit allocation"
                else "credit_grant"
            ),
            "delta": (
                -int(row["amount"])
                if row["entry_type"] == "usage"
                else int(row["amount"])
            ),
            "balance_after": int(row["balance_after"]),
            "status": row["status"],
            "description": row["description"],
        }
        for row in rows
    ]
    return {"entries": entries, "total": int(rows[0]["total_count"]) if rows else 0}


def create_request(
    message: Optional[str] = None, *, ctx: Optional[TenantContext] = None
) -> dict[str, Any]:
    tenant = _ctx(ctx)
    try:
        with get_cursor(commit=True, ctx=tenant) as cur:
            cur.execute(
                "SELECT * FROM create_credit_request(%s, %s, %s, %s, %s)",
                (
                    tenant.org_id,
                    principal_for(tenant),
                    tenant.user_id,
                    default_lifetime_credits(),
                    message,
                ),
            )
            row = cur.fetchone()
    except psycopg2.Error as exc:
        raise _database_error(exc) from exc
    return {
        "id": str(row["id"]),
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
    }


def grant(
    amount: int,
    idempotency_key: str,
    *,
    metadata: Optional[dict[str, Any]] = None,
    ctx: Optional[TenantContext] = None,
) -> dict[str, Any]:
    """Administrative helper; first use creates the default allocation, then grants.

    There is intentionally no public grant API.
    """
    tenant = _ctx(ctx)
    try:
        with get_cursor(commit=True, ctx=tenant) as cur:
            cur.execute(
                "SELECT * FROM grant_credits(%s, %s, %s, %s, %s, %s, %s::jsonb)",
                (
                    tenant.org_id,
                    principal_for(tenant),
                    tenant.user_id,
                    amount,
                    idempotency_key,
                    default_lifetime_credits(),
                    json.dumps(metadata or {}),
                ),
            )
            row = cur.fetchone()
    except psycopg2.Error as exc:
        raise _database_error(exc) from exc
    return dict(row)


def request_idempotency_key(request: Any, feature: CreditFeature) -> str:
    supplied = request.headers.get("X-Idempotency-Key")
    request_id = supplied or getattr(request.state, "request_id", None)
    if not request_id:
        raise ValueError("Request id is unavailable")
    return f"{feature.value}:{request_id}"


def enforce(
    feature: CreditFeature,
    *,
    release_if: Optional[Callable[[Any], bool]] = None,
) -> Callable:
    """Reserve/commit around a FastAPI endpoint while preserving its signature."""

    def decorate(func: Callable) -> Callable:
        signature = inspect.signature(func)

        def prepare(args: tuple, kwargs: dict) -> tuple[Reservation, TenantContext]:
            bound = signature.bind_partial(*args, **kwargs)
            request = bound.arguments.get("request")
            tenant = bound.arguments.get("ctx") or require_current_tenant()
            return reserve(
                feature, request_idempotency_key(request, feature), ctx=tenant
            ), tenant

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapped(*args, **kwargs):
                reservation, tenant = prepare(args, kwargs)
                try:
                    result = await func(*args, **kwargs)
                except BaseException:
                    release(reservation.id, ctx=tenant)
                    raise
                if release_if and release_if(result):
                    release(reservation.id, ctx=tenant)
                else:
                    commit(reservation.id, ctx=tenant)
                return result

            return async_wrapped

        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            reservation, tenant = prepare(args, kwargs)
            try:
                result = func(*args, **kwargs)
            except BaseException:
                release(reservation.id, ctx=tenant)
                raise
            if release_if and release_if(result):
                release(reservation.id, ctx=tenant)
            else:
                commit(reservation.id, ctx=tenant)
            return result

        return wrapped

    return decorate
