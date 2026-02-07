"""
FastAPI application entry point.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

# Load .env from project root (parent of backend/)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
from fastapi.middleware.cors import CORSMiddleware

from app.routers import chat, ingest, monitor, settings

# Ingestion logs: visible in console with [ingest] prefix
_log = logging.getLogger("jarvis.ingest")
if not _log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _log.addHandler(_handler)
    _log.setLevel(logging.INFO)

app = FastAPI(
    title="Jarvis API",
    description="Proactive Financial Agent – ingestion, monitor, chat",
    version="0.1.0",
)

# Allow frontend (Next.js dev server) to call the API
origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").strip().split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(monitor.router, prefix="/api/monitor", tags=["monitor"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])

@app.get("/health")
def health():
    return {"status": "ok"}
