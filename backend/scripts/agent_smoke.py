#!/usr/bin/env python3
"""
Live end-to-end agent smoke test.

Runs ONE real agent cycle exactly as production would — POST-equivalent run
creation, credit reservation, job enqueue, worker drain, LangGraph execution
(plan → tools → synthesize → cross-model review → finalize), step timeline,
conversation append, credit commit — against:

- an EMBEDDED throwaway Postgres (pgserver) with all Alembic migrations and
  the RLS-enforced kritifin_app role — production data is never touched;
- your REAL LLM provider keys from the project .env (Groq, Cerebras, Gemini,
  Moonshot, OpenRouter, DeepSeek, OpenAI — whatever is set), through the real
  quota-aware gateway with Postgres RPM/RPD counters.

Qdrant/document search is intentionally not configured: if the planner picks
search_documents the tool records an ERROR step and the run continues —
which also demonstrates per-tool resilience.

Usage (from backend/): python scripts/agent_smoke.py [--query "..."]
Requires: pip install -r requirements-dev.txt (pgserver).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Environment: real provider keys only; everything else stays isolated.
# Must happen BEFORE any app module import.
# ---------------------------------------------------------------------------
_PROVIDER_KEYS = (
    "GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
    "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY",
)


def _load_provider_keys() -> None:
    env_path = BACKEND_DIR.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() in _PROVIDER_KEYS and value.strip():
            os.environ.setdefault(name.strip(), value.strip())


_load_provider_keys()
# Isolate from the real deployment: no Qdrant, no Supabase auth, no pins.
for name in ("QDRANT_URL", "QDRANT_API_KEY", "QDRANT_COLLECTION", "SUPABASE_URL",
             "SUPABASE_JWT_SECRET", "SUPABASE_SERVICE_ROLE_KEY", "WORKER_FUNCTION_NAME",
             "LLM_MODEL", "BRIEF_LLM_MODEL", "DRAFT_LLM_MODEL", "LLM_PROVIDER"):
    os.environ[name] = ""
os.environ["AUTH_MODE"] = "demo"
os.environ["LOG_FORMAT"] = "text"
os.environ["LOG_LEVEL"] = "INFO"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["DB_POOL_MAX"] = "5"

_APP_ROLE_PASSWORD = "kritifin-app-smoke-password"


def _boot_embedded_postgres():
    """Throwaway Postgres with migrations + the production runtime role."""
    import pgserver
    import psycopg2
    from alembic import command
    from alembic.config import Config

    data_dir = tempfile.mkdtemp(prefix="kritifin-agent-smoke-")
    server = pgserver.get_server(data_dir)
    admin_url = server.get_uri()

    os.environ["DATABASE_ADMIN_URL"] = admin_url
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option(
        "sqlalchemy.url", admin_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    )
    command.upgrade(cfg, "head")

    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"ALTER ROLE kritifin_app LOGIN PASSWORD '{_APP_ROLE_PASSWORD}'")
        cur.execute("GRANT SELECT ON alembic_version TO kritifin_app")
    conn.close()

    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(admin_url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    app_url = urlunparse(
        parsed._replace(netloc=f"kritifin_app:{_APP_ROLE_PASSWORD}@{host}{port}")
    )
    os.environ["DATABASE_URL"] = app_url
    return server, admin_url


def _seed(admin_url: str) -> str:
    """Default workspace + a small client book with alerts. Returns org id."""
    import psycopg2

    org_id = "00000000-0000-0000-0000-000000000001"
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO organizations (id, name) VALUES (%s, 'Smoke Workspace') "
            "ON CONFLICT (id) DO NOTHING",
            (org_id,),
        )
        cur.execute(
            """
            INSERT INTO clients (org_id, full_name, risk_score, total_assets,
                                 cash_savings, last_review_date)
            VALUES (%s, 'Alan Partridge', 5, 895000, 62000, '2025-04-10'),
                   (%s, 'David Chen', 6, 620000, 62000, CURRENT_DATE - 60),
                   (%s, 'Priya Sharma', 4, 310000, 40000, NULL)
            """,
            (org_id, org_id, org_id),
        )
        cur.execute("SELECT id FROM clients WHERE full_name = 'Alan Partridge'")
        alan_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO alerts (org_id, client_id, trigger_date, type, priority, title, status)
            VALUES (%s, %s, CURRENT_DATE + 7, 'DEADLINE', 'HIGH', 'Annual review due', 'PENDING'),
                   (%s, %s, CURRENT_DATE - 12, 'FOLLOW_UP', 'MEDIUM',
                    'Waiting on client: pension decision', 'PENDING')
            """,
            (org_id, alan_id, org_id, alan_id),
        )
    conn.close()
    return org_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        default="Which clients have overdue reviews or follow-ups, and who should I contact first?",
    )
    args = parser.parse_args()

    print("=" * 78)
    print("KritiFin agent smoke test — real providers, embedded Postgres")
    print("=" * 78)

    print("\n[1/6] Booting embedded Postgres + running all migrations…")
    server, admin_url = _boot_embedded_postgres()

    try:
        from app.logging_config import configure_logging

        configure_logging()

        from app.context import TenantContext, set_current_tenant
        from app.services import agent_runs, conversations, credits, jobs
        from app.services.model_gateway import configured_providers
        from app.worker import drain_queue

        providers = configured_providers()
        if not providers:
            print("No provider keys found in .env — aborting.")
            return 2
        print(f"      Providers configured: {', '.join(providers)}")

        print("\n[2/6] Seeding demo workspace (3 clients, 2 alerts)…")
        org_id = _seed(admin_url)
        ctx = TenantContext(org_id=org_id, user_id=None, role="demo")
        set_current_tenant(ctx)

        print("\n[3/6] Creating agent run + reserving 1 credit + enqueueing job…")
        conversation_id = conversations.create(ctx=ctx)
        reservation = credits.reserve(
            credits.CreditFeature.CHAT, f"smoke:{int(time.time())}", ctx=ctx
        )
        run = agent_runs.create(
            kind="copilot",
            input_payload={"query": args.query},
            conversation_id=conversation_id,
            ctx=ctx,
        )
        import uuid as _uuid

        jobs.create(
            str(_uuid.uuid4()),
            kind="agent_run",
            payload={"run_id": run["id"], "credit_reservation_id": reservation.id},
            ctx=ctx,
        )
        print(f"      run_id={run['id']}")
        print(f"      query: {args.query!r}")

        print("\n[4/6] Draining the job queue (worker path — watch the real LLM calls):\n")
        set_current_tenant(None)  # the worker binds its own context per job
        started = time.monotonic()
        stats = drain_queue(lambda: 10_000_000)
        elapsed = round(time.monotonic() - started, 1)
        print(f"\n      drain: processed={stats.processed} in {elapsed}s")

        print("\n[5/6] Run result:")
        set_current_tenant(ctx)
        final = agent_runs.get(run["id"], ctx=ctx)
        steps = agent_runs.get_steps(run["id"], ctx=ctx)
        print(f"      status: {final['status']}")
        print("\n      Timeline (agent_steps):")
        for s in steps:
            detail = s.get("detail") or {}
            extra = detail.get("model") or detail.get("summary") or detail.get("verdict") or ""
            print(f"        {s['seq']:>2}. [{s['status']:<5}] {s['label']:<28} {extra}")
        output = final.get("output") or {}
        review = output.get("review") or {}
        print(f"\n      Models used: {json.dumps(output.get('model_labels') or {})}")
        print(f"      Review verdict: {review.get('verdict')}  issues={review.get('issues')}")
        print(f"      Plan reason: {output.get('plan_reason')!r}")
        print("\n      ANSWER:")
        for line in (output.get("answer") or "(none)").splitlines():
            print(f"        {line}")

        messages = conversations.get_messages(conversation_id, ctx=ctx)
        summary = credits.get_summary(ctx=ctx)
        print(f"\n[6/6] Conversation messages persisted: {len(messages)} "
              f"| credits used: {summary['used']}/{summary['total_granted']}")

        # Quota counters prove the Postgres RPM/RPD accounting ran.
        import psycopg2

        conn = psycopg2.connect(admin_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT provider, model, window_kind, request_count "
                "FROM llm_quota_counters ORDER BY provider, model, window_kind"
            )
            rows = cur.fetchall()
        conn.close()
        print("\n      llm_quota_counters (Postgres quota accounting):")
        for provider, model, kind, count in rows:
            print(f"        {provider:<10} {model:<40} {kind:<7} {count}")

        ok = final["status"] == "DONE" and bool(output.get("answer"))
        print("\n" + "=" * 78)
        print("SMOKE TEST PASSED" if ok else "SMOKE TEST FAILED")
        print("=" * 78)
        return 0 if ok else 1
    finally:
        from app.db import close_pool

        close_pool()
        server.cleanup()


if __name__ == "__main__":
    sys.exit(main())
