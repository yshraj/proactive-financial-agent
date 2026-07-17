"""
Sentry initialisation and readiness checks.

Sentry is enabled only when SENTRY_DSN is set. PII is scrubbed: default PII is
off, request bodies are never attached, and a before_send hook strips known
sensitive keys — client data and generated output must never reach Sentry.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger("jarvis.observability")

_SENSITIVE_KEYS = ("authorization", "x-api-key", "cookie", "set-cookie")


def _scrub_event(event: dict, hint: Any) -> Optional[dict]:
    request = event.get("request") or {}
    headers = request.get("headers")
    if isinstance(headers, dict):
        for key in list(headers):
            if key.lower() in _SENSITIVE_KEYS:
                headers[key] = "[redacted]"
    # Never ship request bodies (uploads / adviser notes / chat queries).
    request.pop("data", None)
    if request:
        event["request"] = request
    return event


def init_sentry() -> bool:
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("ENV", os.environ.get("ENVIRONMENT", "development")),
            release=os.environ.get("RELEASE_SHA") or None,
            send_default_pii=False,
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            before_send=_scrub_event,
            integrations=[StarletteIntegration(), FastApiIntegration()],
        )
        logger.info("Sentry initialised (env=%s)", os.environ.get("ENV", "development"))
        return True
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed.")
        return False


# ---------------------------------------------------------------------------
# Readiness: deep health with a short cache so probes stay cheap.
# ---------------------------------------------------------------------------

_READY_CACHE_SECONDS = 10.0
_ready_cache: "tuple[float, dict] | None" = None


def _check_database() -> dict:
    from app.db import get_cursor

    started = time.monotonic()
    try:
        with get_cursor() as cur:  # no tenant: plain SELECT 1, no table access
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
        return {"ok": True, "latency_ms": round((time.monotonic() - started) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001 - readiness must not raise
        return {"ok": False, "error": type(exc).__name__}


def _check_qdrant() -> dict:
    if not os.environ.get("QDRANT_URL"):
        return {"ok": False, "error": "QDRANT_URL not configured"}
    from app.services.clients import get_qdrant_client
    from app.services.config import QDRANT_COLLECTION

    started = time.monotonic()
    try:
        client = get_qdrant_client()
        exists = client.collection_exists(QDRANT_COLLECTION)
        return {
            "ok": bool(exists),
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            **({} if exists else {"error": f"collection '{QDRANT_COLLECTION}' missing"}),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}


def _migration_version() -> Optional[str]:
    from app.db import get_cursor

    try:
        with get_cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version")
            row = cur.fetchone()
        return row["version_num"] if row else None
    except Exception:
        return None


def readiness_report(force: bool = False) -> dict:
    """Deep readiness: DB, Qdrant, auth posture, migration version. Cached."""
    global _ready_cache
    now = time.monotonic()
    if not force and _ready_cache is not None and now - _ready_cache[0] < _READY_CACHE_SECONDS:
        return _ready_cache[1]

    from app import security

    checks = {
        "database": _check_database(),
        "qdrant": _check_qdrant(),
        "llm_configured": {"ok": bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))},
    }
    report = {
        "status": "ok" if all(c.get("ok") for c in checks.values()) else "degraded",
        "auth_mode": security.auth_mode(),
        "migration_version": _migration_version(),
        "checks": checks,
    }
    _ready_cache = (now, report)
    return report
