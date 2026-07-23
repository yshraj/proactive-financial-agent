"""
FastAPI application entry point.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

# Load .env from project root (parent of backend/)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# On Lambda, secrets live in SSM Parameter Store, not function env vars.
# Must run before Sentry/DB/LLM clients read the environment. No-op locally.
from app.secrets_loader import load_secrets

load_secrets()

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from datetime import datetime, timedelta, timezone

from app import context as request_context
from app import security
from app.auth import authenticate_request, require_access_code
from app.logging_config import configure_logging
from app.observability import init_sentry, readiness_report
from app.routers import chat, compliance, credits, ingest, monitor, settings
from app.security import enforce_auth_mode, limiter
from app.services.credits import (
    CreditBalanceUnavailable,
    DuplicateCreditAction,
    InsufficientCredits,
)
from app.services.llm import AIUnavailableError
from app.services.safety import (
    detail_to_message,
    error_envelope,
    public_error_message,
)

configure_logging()
init_sentry()

logger = logging.getLogger("jarvis.api")
access_logger = logging.getLogger("jarvis.access")
ratelimit_logger = logging.getLogger("jarvis.ratelimit")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail closed before accepting traffic: unsafe auth config refuses to boot.
    enforce_auth_mode()
    # Loudly name every unset-but-expected var (access code, LLM key, CORS, …)
    # so a misconfigured deploy is obvious in the logs, not a silent surprise.
    from app.observability import log_startup_config

    log_startup_config(logger)
    # Queued jobs are drained event-driven (services/worker_trigger.py): the
    # worker Lambda in AWS, or a background task locally. No polling loop.
    yield
    from app.db import close_pool

    close_pool()


app = FastAPI(
    title="KritiFin API",
    description="Proactive Financial Agent – ingestion, monitor, chat",
    version="0.2.0",
    lifespan=lifespan,
)

# Rate limiting (per org/user, per-session in demo, IP fallback).
app.state.limiter = limiter

# ---------------------------------------------------------------------------
# Error responses. Every error carries BOTH:
# - "detail": the FastAPI-native payload (string / dict / validation list) that
#   existing clients and tests already consume, and
# - "error": {code, message, retryable} — one machine-readable envelope so the
#   frontend can branch on codes instead of matching message strings.
# Messages are always fixed, friendly copy — never str(exc) (see
# app.services.safety.public_error_message for the leak policy).
# ---------------------------------------------------------------------------


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Wrap every HTTPException with the structured error envelope."""
    message = detail_to_message(exc.detail, exc.status_code)
    code = None
    if isinstance(exc.detail, dict):
        raw_code = exc.detail.get("code")
        if isinstance(raw_code, str) and raw_code:
            code = raw_code.lower()
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(
            {
                "detail": exc.detail,
                "error": error_envelope(exc.status_code, message, code=code),
            }
        ),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Structured 422: keep FastAPI's field details, add a friendly envelope."""
    message = "Some fields are invalid. Please review and try again."
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(exc.errors()),
            "error": error_envelope(422, message),
        },
    )


@app.exception_handler(AIUnavailableError)
async def ai_unavailable_handler(request: Request, exc: AIUnavailableError):
    """LLM provider failure: clean 503, provider error stays in the logs."""
    message = str(exc) or public_error_message("ai_unavailable")
    return JSONResponse(
        status_code=503,
        content={
            "detail": message,
            "error": error_envelope(503, message, code="ai_unavailable"),
        },
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Structured 429 for a tripped limit, plus a queryable hit log.

    Wraps slowapi's default handler to inherit correct Retry-After / rate-limit
    headers, then replaces the body with a machine-readable shape the frontend
    can branch on, and emits one structured log line per hit (session/limit
    type/timestamp) to diagnose abuse-protection events.
    """
    default = _rate_limit_exceeded_handler(request, exc)
    scope = getattr(getattr(exc, "limit", None), "scope", None)
    limit_type = security.limit_type_for(scope, request.url.path)

    # Short-window abuse protection uses the same per-user/session key as the
    # limiter. Lifetime credits are enforced by the separate credit ledger.
    rate_limit_key = security._rate_limit_key(request)

    retry_after = default.headers.get("Retry-After")
    reset_at = None
    if retry_after and str(retry_after).isdigit():
        reset_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(retry_after))
        ).isoformat()

    ratelimit_logger.warning(
        "rate limit exceeded: %s on %s",
        limit_type,
        request.url.path,
        extra={
            "event": "rate_limit_hit",
            "limit_type": limit_type,
            "rate_limit_key": rate_limit_key,
            "path": request.url.path,
            "method": request.method,
            "request_id": getattr(request.state, "request_id", ""),
        },
    )

    message = "Too many requests. Please wait a moment and try again."
    response = JSONResponse(
        status_code=429,
        content={
            "error": error_envelope(429, message, code="rate_limited", retryable=True),
            "limit_type": limit_type,
            "reset_at": reset_at,
            "detail": message,
        },
    )
    # Preserve rate-limit headers slowapi computed on the default response.
    for header in ("Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
        if header in default.headers:
            response.headers[header] = default.headers[header]
    return response


@app.exception_handler(InsufficientCredits)
async def insufficient_credits_handler(request: Request, exc: InsufficientCredits):
    message = "You don't have enough AI credits for this action."
    return JSONResponse(
        status_code=409,
        content={
            "error": error_envelope(
                409, message, code="insufficient_credits", retryable=False
            ),
            "detail": message,
            "required": exc.required,
            "remaining": exc.remaining,
            "feature": exc.feature,
            "contact_available": (
                os.environ.get("CREDIT_REQUEST_ENABLED", "true").lower()
                in ("1", "true", "yes")
                or bool(os.environ.get("CREDIT_CONTACT_EMAIL", "").strip())
            ),
        },
    )


@app.exception_handler(CreditBalanceUnavailable)
async def credit_balance_unavailable_handler(
    request: Request, exc: CreditBalanceUnavailable
):
    message = "Credit balance is temporarily unavailable. Please try again."
    return JSONResponse(
        status_code=503,
        content={
            "error": error_envelope(
                503, message, code="credit_balance_unavailable", retryable=True
            ),
            "detail": message,
        },
    )


@app.exception_handler(DuplicateCreditAction)
async def duplicate_credit_action_handler(
    request: Request, exc: DuplicateCreditAction
):
    message = "This idempotent AI action has already been processed."
    return JSONResponse(
        status_code=409,
        content={
            "error": error_envelope(
                409, message, code="duplicate_credit_action", retryable=False
            ),
            "detail": message,
            "feature": exc.feature,
            "status": exc.status,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort handler: log with correlation, return a safe message.

    Re-raising is avoided so stack traces never leak; Sentry still receives the
    event via its ASGI middleware, which observes the exception before us.
    """
    logger.exception(
        "Unhandled error on %s %s: %s", request.method, request.url.path, exc
    )
    message = public_error_message("internal", exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": message,
            "error": error_envelope(500, message, retryable=True),
        },
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


# CORS: explicit origins; Bearer-token auth means no cookies -> no credentials.
origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").strip().split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization", "Content-Type", "X-API-Key", "X-Request-ID",
        "X-Access-Code", "X-Session-Id", "X-Idempotency-Key",
    ],
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind the request id for log correlation, emit an access log line, and
    attach security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        request_context.set_request_id(request_id)
        request_context.set_current_tenant(None)  # never inherit across requests
        started = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            request_context.set_current_tenant(None)
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        if request.url.path not in ("/health", "/health/ready"):
            access_logger.info(
                "%s %s -> %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(RequestContextMiddleware)

# API guard: the shared access-code front door runs first (rejects unknown
# callers before any tenant work), then auth resolves a tenant (Supabase JWT,
# service API key, or — only when AUTH_MODE=demo — the shared demo workspace).
api_guard = [Depends(require_access_code), Depends(authenticate_request)]
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"], dependencies=api_guard)
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitor"], dependencies=api_guard)
app.include_router(chat.router, prefix="/api/chat", tags=["chat"], dependencies=api_guard)
app.include_router(settings.router, prefix="/api/settings", tags=["settings"], dependencies=api_guard)
app.include_router(compliance.router, prefix="/api/compliance", tags=["compliance"], dependencies=api_guard)
app.include_router(credits.router, prefix="/api/credits", tags=["credits"], dependencies=api_guard)


@app.get("/api/access/check", dependencies=[Depends(require_access_code)])
def access_check():
    """Front-door probe: 200 if the access code is valid (or the gate is off),
    401 otherwise. Lets the frontend gate the app shell without a tenant/token."""
    return {"ok": True}


@app.get("/health")
def health():
    """Liveness: no dependency checks (cheap, unauthenticated)."""
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    """Readiness: DB + Qdrant + auth posture + migration version (cached 10s)."""
    report = readiness_report()
    status_code = 200 if report["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=report)
