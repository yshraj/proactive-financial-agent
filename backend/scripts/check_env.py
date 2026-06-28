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
        "DATABASE_URL", "QDRANT_URL", "QDRANT_API_KEY", "OPENAI_API_KEY",
        "LLM_PROVIDER", "EMBEDDING_PROVIDER", "EMBEDDING_MODEL",
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "COHERE_API_KEY",
        "API_KEY", "ALLOW_DATA_RESET", "QDRANT_COLLECTION", "ADVISER_ID",
    )}

    llm = (env["LLM_PROVIDER"] or "openai").lower()
    emb = (env["EMBEDDING_PROVIDER"] or "openai").lower()

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

    # LLM provider keys
    section(f"Provider keys (LLM_PROVIDER={llm}, EMBEDDING_PROVIDER={emb})")
    needs_openai = llm == "openai" or emb == "openai"
    if needs_openai:
        key = env["OPENAI_API_KEY"]
        if not key:
            fail("OPENAI_API_KEY is required (openai is used for LLM and/or embeddings) but missing")
        elif is_placeholder(key) or not key.startswith("sk-"):
            fail("OPENAI_API_KEY looks invalid (should start with 'sk-')")
        else:
            ok(f"OPENAI_API_KEY present ({mask(key)})")
    if llm == "gemini" and not (env["GEMINI_API_KEY"] or env["GOOGLE_API_KEY"]):
        fail("LLM_PROVIDER=gemini but neither GEMINI_API_KEY nor GOOGLE_API_KEY is set")
    if emb == "cohere" and not env["COHERE_API_KEY"]:
        fail("EMBEDDING_PROVIDER=cohere but COHERE_API_KEY is missing")

    # Embedding dimension sanity (Qdrant collection is created at 1536)
    model = env["EMBEDDING_MODEL"] or "text-embedding-3-small"
    if emb == "openai" and model not in ("text-embedding-3-small", "text-embedding-ada-002"):
        warn(f"EMBEDDING_MODEL='{model}' may not be 1536-dim; the Qdrant collection is created at 1536. Mismatch will break RAG upserts/search.")
    else:
        ok(f"EMBEDDING_MODEL={model}")

    # Optional / security
    section("Optional & security (M0)")
    if env["API_KEY"]:
        ok(f"API_KEY set ({mask(env['API_KEY'])}) — API requires X-API-Key")
    else:
        warn("API_KEY not set — the backend API is UNAUTHENTICATED (fine for local dev; set in production).")
    if env["ALLOW_DATA_RESET"].lower() in ("1", "true", "yes"):
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
        for t in ("clients", "alerts", "ingested_documents"):
            (ok if t in tables else fail)(
                f"Postgres: table '{t}' " + ("exists" if t in tables else "MISSING — run backend/supabase_schema.sql")
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
            target = env.get("QDRANT_COLLECTION") or "client_memory"
            if target in cols:
                ci = httpx.get(env["QDRANT_URL"].rstrip("/") + f"/collections/{target}", headers=headers, timeout=10)
                size = ci.json().get("result", {}).get("config", {}).get("params", {}).get("vectors", {})
                dim = size.get("size") if isinstance(size, dict) else None
                if dim == 1536:
                    ok(f"Qdrant: collection '{target}' exists with 1536-dim vectors")
                elif dim is not None:
                    fail(f"Qdrant: collection '{target}' has {dim}-dim vectors (expected 1536)")
                else:
                    ok(f"Qdrant: collection '{target}' exists")
            else:
                warn(f"Qdrant: collection '{target}' not found — run scripts/create_qdrant_collection.py")
        else:
            fail(f"Qdrant: HTTP {r.status_code} — check URL/API key")
    except Exception as e:  # noqa: BLE001
        fail(f"Qdrant: connection failed — {type(e).__name__}: {e}")

    # OpenAI (free metadata call, no token spend)
    if (env.get("LLM_PROVIDER") or "openai").lower() == "openai" or (
        env.get("EMBEDDING_PROVIDER") or "openai"
    ).lower() == "openai":
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
