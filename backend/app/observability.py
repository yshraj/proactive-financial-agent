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
            environment=os.environ.get("ENV", "development"),
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
# Startup config audit: name every unset-but-expected var loudly, so a
# misconfigured deploy shows up in the logs instead of failing mysteriously.
# ---------------------------------------------------------------------------


def _unset(name: str) -> bool:
    return not (os.environ.get(name) or "").strip()


def startup_config_warnings() -> list[str]:
    """Human-readable warnings for missing/defaulted config. Non-fatal: hard
    requirements (auth posture, DATABASE_URL on first query) fail elsewhere;
    this surfaces the quieter foot-guns a deploy tends to forget."""
    from app import security

    warnings: list[str] = []

    # Data plane.
    if _unset("DATABASE_URL"):
        warnings.append("DATABASE_URL is not set — the backend cannot reach Postgres.")
    if _unset("QDRANT_URL"):
        warnings.append("QDRANT_URL is not set — RAG/semantic search will be unavailable.")

    # LLM providers: completions route through the multi-provider gateway
    # (any one key is enough). Embeddings default to local fastembed and
    # need no key; only the legacy openai embeddings provider requires one.
    from app.services.model_gateway import configured_providers

    providers = configured_providers()
    if not providers:
        warnings.append(
            "No LLM provider key is set (GROQ_API_KEY / CEREBRAS_API_KEY / GEMINI_API_KEY / "
            "MOONSHOT_API_KEY / OPENROUTER_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY) — "
            "AI features fall back to deterministic stubs."
        )
    embeddings_provider = (os.environ.get("EMBEDDINGS_PROVIDER") or "fastembed").strip().lower()
    if embeddings_provider == "openai" and _unset("OPENAI_API_KEY"):
        warnings.append(
            "EMBEDDINGS_PROVIDER=openai but OPENAI_API_KEY is not set — RAG indexing/search "
            "will fail. Unset EMBEDDINGS_PROVIDER to use the local fastembed default."
        )

    # Front door: demo mode with no shared code = a fully open public API.
    if security.demo_mode_enabled() and not security.access_code_configured():
        warnings.append(
            "AUTH_MODE=demo and ACCESS_CODE is unset — the API is open to anyone with "
            "the URL. Set ACCESS_CODE to enable the shared front-door gate."
        )

    # CORS: the default only allows localhost, which blocks a real frontend origin.
    if _unset("CORS_ORIGINS"):
        warnings.append(
            "CORS_ORIGINS is not set — defaulting to http://localhost:3000; browser "
            "calls from your deployed frontend origin will be blocked by CORS."
        )

    # Observability.
    if _unset("SENTRY_DSN"):
        warnings.append("SENTRY_DSN is not set — backend error reporting is disabled (structured logs only).")

    return warnings


def log_startup_config(target_logger: logging.Logger) -> None:
    """Emit the config audit at startup (WARNING per finding, or a clear all-good)."""
    findings = startup_config_warnings()
    if not findings:
        target_logger.info("Config audit: all expected environment variables are set.")
        return
    for w in findings:
        target_logger.warning("CONFIG: %s", w)


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
