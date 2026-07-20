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

from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from datetime import datetime, timedelta, timezone

from app import context as request_context
from app import security
from app.auth import authenticate_request, require_access_code
from app.logging_config import configure_logging
from app.observability import init_sentry, readiness_report
from app.routers import chat, compliance, ingest, monitor, settings
from app.security import enforce_auth_mode, limiter
from app.services.safety import public_error_message

configure_logging()
init_sentry()

logger = logging.getLogger("jarvis.api")
access_logger = logging.getLogger("jarvis.access")
ratelimit_logger = logging.getLogger("jarvis.ratelimit")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail closed before accepting traffic: unsafe auth config refuses to boot.
    enforce_auth_mode()
    # Demo mode with no shared access code = a fully open public door. Allowed
    # (local dev / previews) but loudly flagged so a deploy doesn't do it silently.
    from app.security import access_code_configured, demo_mode_enabled

    if demo_mode_enabled() and not access_code_configured():
        logger.warning(
            "AUTH_MODE=demo and ACCESS_CODE is unset — the API is open to anyone "
            "with the URL. Set ACCESS_CODE to enable the shared front-door gate."
        )
    # Single-service deployments process queued jobs in-process; render.yaml
    # disables this (INLINE_WORKER=false) once the dedicated worker exists.
    inline_worker_stop = None
    if os.environ.get("INLINE_WORKER", "true").lower() in ("1", "true", "yes"):
        from app.worker import start_inline_worker

        inline_worker_stop = start_inline_worker()
    yield
    if inline_worker_stop is not None:
        inline_worker_stop.set()
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


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Structured 429 for a tripped limit, plus a queryable hit log.

    Wraps slowapi's default handler to inherit correct Retry-After / rate-limit
    headers, then replaces the body with a machine-readable shape the frontend
    can branch on, and emits one structured log line per hit (session/limit
    type/timestamp) to inform later pricing decisions.
    """
    default = _rate_limit_exceeded_handler(request, exc)
    scope = getattr(getattr(exc, "limit", None), "scope", None)
    limit_type = security.limit_type_for(scope, request.url.path)

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
            "rate_limit_key": security._rate_limit_key(request),
            "path": request.url.path,
            "method": request.method,
            "request_id": getattr(request.state, "request_id", ""),
        },
    )

    response = JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit",
            "limit_type": limit_type,
            "reset_at": reset_at,
            "detail": "You've reached the demo usage limit. Please try again later.",
        },
    )
    # Preserve rate-limit headers slowapi computed on the default response.
    for header in ("Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
        if header in default.headers:
            response.headers[header] = default.headers[header]
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort handler: log with correlation, return a safe message.

    Re-raising is avoided so stack traces never leak; Sentry still receives the
    event via its ASGI middleware, which observes the exception before us.
    """
    logger.exception(
        "Unhandled error on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=500,
        content={"detail": public_error_message("internal", exc)},
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
        "X-Access-Code", "X-Session-Id",
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
