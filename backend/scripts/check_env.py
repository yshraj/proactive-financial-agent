#!/usr/bin/env python3
"""
Validate the project's .env configuration.

Usage (from backend/, with the venv active):
    python scripts/check_env.py            # format/presence checks only (no network)
    python scripts/check_env.py --connect  # also test Postgres / Qdrant / OpenAI live

Secrets are masked in all output. Exit code is non-zero if any required check fails,
so this can gate CI / a pre-deploy step.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

errors: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(f"{GREEN}  PASS{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"{RED}  FAIL{RESET} {msg}")
    errors.append(msg)


def warn(msg: str) -> None:
    print(f"{YELLOW}  WARN{RESET} {msg}")
    warnings.append(msg)


def mask(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 10:
        return value[0] + "***"
    return value[:4] + "…" + value[-4:]


PLACEHOLDERS = (
    "YOUR-PASSWORD",
    "your-cluster-id",
    "PROJECT_REF",
    "sk-...",
    "REGION",
)


def is_placeholder(value: str) -> bool:
    return any(p in value for p in PLACEHOLDERS)


def section(title: str) -> None:
    print(f"\n{title}")


def check_presence() -> dict:
    section("Loading .env")
    if not ENV_PATH.exists():
        fail(f".env not found at project root ({ENV_PATH})")
        return {}
    load_dotenv(ENV_PATH)
    ok(f".env found at {ENV_PATH}")

    env = {k: (os.environ.get(k) or "").strip() for k in (
        "DATABASE_URL", "DATABASE_ADMIN_URL", "QDRANT_URL", "QDRANT_API_KEY",
        "OPENAI_API_KEY", "EMBEDDINGS_PROVIDER", "EMBEDDING_MODEL", "FASTEMBED_MODEL",
        "GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
        "MOONSHOT_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY",
        "API_KEY", "ALLOW_DATA_RESET", "QDRANT_COLLECTION",
        "AUTH_MODE", "SUPABASE_URL", "SUPABASE_JWT_SECRET",
        "SUPABASE_SERVICE_ROLE_KEY", "SENTRY_DSN", "ENV",
    )}

    section("Required variables")
    # DATABASE_URL
    db = env["DATABASE_URL"]
    if not db:
        fail("DATABASE_URL is missing")
    elif is_placeholder(db):
        fail("DATABASE_URL still contains a placeholder")
    else:
        parsed = urlparse(db)
        if parsed.scheme not in ("postgresql", "postgres"):
            fail(f"DATABASE_URL scheme should be postgresql, got '{parsed.scheme}'")
        elif not parsed.hostname or not parsed.username:
            fail("DATABASE_URL is missing host or user")
        else:
            port = parsed.port or 5432
            ok(f"DATABASE_URL → host={parsed.hostname} port={port} db={parsed.path.lstrip('/') or '?'} user={mask(parsed.username)}")
            if "pooler.supabase.com" in (parsed.hostname or "") and port == 5432:
                warn("Using Supabase pooler on port 5432 (session mode). For serverless/many short connections, 6543 (transaction mode) is usually recommended.")

    # QDRANT
    qurl = env["QDRANT_URL"]
    if not qurl:
        fail("QDRANT_URL is missing")
    elif is_placeholder(qurl):
        fail("QDRANT_URL still contains a placeholder")
    elif not qurl.startswith("http"):
        fail("QDRANT_URL should start with http(s)://")
    else:
        ok(f"QDRANT_URL → {qurl}")
        if "cloud.qdrant.io" in qurl and not env["QDRANT_API_KEY"]:
            fail("QDRANT_URL is Qdrant Cloud but QDRANT_API_KEY is empty")
        elif env["QDRANT_API_KEY"]:
            ok(f"QDRANT_API_KEY present ({mask(env['QDRANT_API_KEY'])})")

    # LLM gateway provider keys (any one is enough; free tiers first).
    section("LLM gateway provider keys")
    gateway_keys = {
        "GROQ_API_KEY": env["GROQ_API_KEY"],
        "CEREBRAS_API_KEY": env["CEREBRAS_API_KEY"],
        "GEMINI_API_KEY": env["GEMINI_API_KEY"] or env["GOOGLE_API_KEY"],
        "MOONSHOT_API_KEY": env["MOONSHOT_API_KEY"],
        "OPENROUTER_API_KEY": env["OPENROUTER_API_KEY"],
        "DEEPSEEK_API_KEY": env["DEEPSEEK_API_KEY"],
        "OPENAI_API_KEY": env["OPENAI_API_KEY"],
    }
    configured = [name for name, value in gateway_keys.items() if value and not is_placeholder(value)]
    if not configured:
        fail("No LLM provider key set — configure at least one (GROQ_API_KEY is the "
             "recommended free-tier default; see .env.example).")
    else:
        for name in configured:
            ok(f"{name} present ({mask(gateway_keys[name])})")

    # Embeddings: local fastembed needs no key; legacy openai needs one.
    embeddings_provider = (env["EMBEDDINGS_PROVIDER"] or "fastembed").lower()
    section(f"Embeddings (provider={embeddings_provider})")
    if embeddings_provider == "openai":
        if not env["OPENAI_API_KEY"]:
            fail("EMBEDDINGS_PROVIDER=openai but OPENAI_API_KEY is missing")
        model = env["EMBEDDING_MODEL"] or "text-embedding-3-small"
        ok(f"EMBEDDING_MODEL={model} (1536-dim legacy collection)")
    else:
        ok(f"fastembed model {env['FASTEMBED_MODEL'] or 'BAAI/bge-small-en-v1.5'} "
           "(local, 384-dim, no API key needed)")

    # Auth posture (fail closed)
    section("Auth posture")
    auth_mode = (env["AUTH_MODE"] or "required").lower()
    supabase_auth = bool(env["SUPABASE_URL"] or env["SUPABASE_JWT_SECRET"])
    is_prod = (env["ENV"] or "").lower() in ("production", "prod")
    if auth_mode == "demo":
        if is_prod:
            fail("AUTH_MODE=demo with ENV=production — the app will refuse to boot.")
        else:
            warn("AUTH_MODE=demo — anonymous access into a shared demo workspace (local/dev only).")
    else:
        if supabase_auth:
            ok("AUTH_MODE=required with Supabase auth configured "
               f"({'JWKS via SUPABASE_URL' if env['SUPABASE_URL'] else 'HS256 secret'})")
        else:
            fail("AUTH_MODE=required (default) but neither SUPABASE_URL nor "
                 "SUPABASE_JWT_SECRET is set — the app will refuse to boot. "
                 "Set AUTH_MODE=demo explicitly for local open mode.")
    if env["API_KEY"]:
        ok(f"API_KEY set ({mask(env['API_KEY'])}) — service callers may use X-API-Key")
    if env["SUPABASE_SERVICE_ROLE_KEY"]:
        ok("SUPABASE_SERVICE_ROLE_KEY set — documents persist to Supabase Storage")
    else:
        warn("SUPABASE_SERVICE_ROLE_KEY not set — uploads fall back to local disk "
             "(EPHEMERAL on Lambda/containers; originals are lost on deploy).")
    if env["SENTRY_DSN"]:
        ok("SENTRY_DSN set — error reporting enabled")
    else:
        warn("SENTRY_DSN not set — no error reporting (recommended for staging/production).")
    if env["DATABASE_ADMIN_URL"]:
        ok("DATABASE_ADMIN_URL set — migrations run as admin; runtime stays least-privilege")
    else:
        warn("DATABASE_ADMIN_URL not set — Alembic will use DATABASE_URL "
             "(fine while it still points at the postgres role).")
    if env["ALLOW_DATA_RESET"].lower() in ("1", "true", "yes", "force"):
        warn("ALLOW_DATA_RESET is enabled — the destructive clear-data endpoint is callable.")
    else:
        ok("ALLOW_DATA_RESET disabled (clear-data blocked)")

    return env


def check_connectivity(env: dict) -> None:
    section("Live connectivity (--connect)")

    # Postgres
    try:
        import psycopg2
        conn = psycopg2.connect(env["DATABASE_URL"], connect_timeout=8)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )
        tables = {r[0] for r in cur.fetchall()}
        ok("Postgres: connected")
        for t in (
            "clients", "alerts", "ingested_documents",
            "organizations", "users", "org_memberships",
            "audit_log", "ai_outputs", "jobs", "conversations",
        ):
            (ok if t in tables else fail)(
                f"Postgres: table '{t}' " + ("exists" if t in tables else "MISSING — run `cd backend && alembic upgrade head`")
            )
        conn.close()
    except Exception as e:  # noqa: BLE001
        fail(f"Postgres: connection failed — {type(e).__name__}: {e}")

    # Qdrant
    try:
        import httpx
        url = env["QDRANT_URL"].rstrip("/") + "/collections"
        headers = {"api-key": env["QDRANT_API_KEY"]} if env["QDRANT_API_KEY"] else {}
        r = httpx.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            cols = [c.get("name") for c in r.json().get("result", {}).get("collections", [])]
            ok(f"Qdrant: connected (collections: {', '.join(cols) or 'none'})")
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from app.services import embeddings as emb
            from app.services.config import QDRANT_COLLECTION as target

            expected_dim = emb.vector_size()
            if target in cols:
                ci = httpx.get(env["QDRANT_URL"].rstrip("/") + f"/collections/{target}", headers=headers, timeout=10)
                size = ci.json().get("result", {}).get("config", {}).get("params", {}).get("vectors", {})
                dim = size.get("size") if isinstance(size, dict) else None
                if dim == expected_dim:
                    ok(f"Qdrant: collection '{target}' exists with {expected_dim}-dim vectors")
                elif dim is not None:
                    fail(f"Qdrant: collection '{target}' has {dim}-dim vectors "
                         f"(expected {expected_dim} for {emb.model_name()})")
                else:
                    ok(f"Qdrant: collection '{target}' exists")
            else:
                warn(f"Qdrant: collection '{target}' not found — created automatically on "
                     "first ingest, or run scripts/create_qdrant_collection.py")
        else:
            fail(f"Qdrant: HTTP {r.status_code} — check URL/API key")
    except Exception as e:  # noqa: BLE001
        fail(f"Qdrant: connection failed — {type(e).__name__}: {e}")

    # OpenAI key validity (free metadata call): only when a key is configured.
    if env["OPENAI_API_KEY"]:
        try:
            import httpx
            r = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {env['OPENAI_API_KEY']}"},
                timeout=10,
            )
            if r.status_code == 200:
                ok("OpenAI: API key valid (models endpoint reachable)")
            elif r.status_code == 401:
                fail("OpenAI: 401 Unauthorized — API key is invalid or revoked")
            else:
                warn(f"OpenAI: unexpected HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            fail(f"OpenAI: request failed — {type(e).__name__}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate .env configuration")
    ap.add_argument("--connect", action="store_true", help="also run live connectivity tests")
    args = ap.parse_args()

    print("Environment configuration check")
    print(f"{DIM}(secrets are masked){RESET}")
    env = check_presence()
    if env and args.connect:
        check_connectivity(env)

    section("Summary")
    if errors:
        print(f"{RED}{len(errors)} error(s){RESET}, {len(warnings)} warning(s). Fix errors before proceeding.")
        return 1
    if warnings:
        print(f"{GREEN}No errors{RESET}, {YELLOW}{len(warnings)} warning(s){RESET}. Safe to proceed; review warnings.")
        return 0
    print(f"{GREEN}All checks passed.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
