"""
FastAPI application entry point.
"""
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request

# Load .env from project root (parent of backend/)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging_config import configure_logging
from app.routers import chat, ingest, monitor, settings
from app.security import limiter, require_api_key

configure_logging()

app = FastAPI(
    title="Jarvis API",
    description="Proactive Financial Agent – ingestion, monitor, chat",
    version="0.1.0",
)

# Rate limiting (per client IP) – limits are declared per-endpoint in routers.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Allow frontend (Next.js dev server) to call the API
origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").strip().split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request id and basic security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(RequestIdMiddleware)

# All API routers require the shared API key (M0 stopgap auth).
api_guard = [Depends(require_api_key)]
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"], dependencies=api_guard)
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitor"], dependencies=api_guard)
app.include_router(chat.router, prefix="/api/chat", tags=["chat"], dependencies=api_guard)
app.include_router(settings.router, prefix="/api/settings", tags=["settings"], dependencies=api_guard)


@app.get("/health")
def health():
    return {"status": "ok"}
