#!/usr/bin/env python3
"""
Diagnose Supabase connectivity without printing credentials.

Reads DATABASE_URL/SUPABASE_URL from the project .env and probes:
1. the configured pooler DSN,
2. the direct database host (db.<ref>.supabase.co) derived from SUPABASE_URL,
3. the project's public REST/auth endpoints (detects a PAUSED project —
   Supabase free-tier projects pause after inactivity and the pooler then
   reports "tenant/user not found").
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values

ENV = dotenv_values(Path(__file__).resolve().parents[2] / ".env")


def probe_pg(name: str, dsn: str) -> None:
    import psycopg2

    try:
        conn = psycopg2.connect(dsn, connect_timeout=10)
        with conn.cursor() as cur:
            cur.execute("SELECT current_user, version()")
            user, _ = cur.fetchone()
        conn.close()
        print(f"  {name}: OK (connected as {user})")
    except Exception as e:  # noqa: BLE001
        msg = str(e).replace("\n", " ")[:180]
        print(f"  {name}: FAIL — {type(e).__name__}: {msg}")


def probe_http(name: str, url: str) -> None:
    import httpx

    try:
        r = httpx.get(url, timeout=12, follow_redirects=True)
        print(f"  {name}: HTTP {r.status_code} — {r.text[:120].strip()}")
    except Exception as e:  # noqa: BLE001
        print(f"  {name}: FAIL — {type(e).__name__}")


def main() -> int:
    db_url = ENV.get("DATABASE_URL") or ""
    supabase_url = (ENV.get("SUPABASE_URL") or "").rstrip("/")
    if not db_url or not supabase_url:
        print("DATABASE_URL / SUPABASE_URL missing from .env")
        return 1

    parsed = urlparse(db_url)
    print(f"Configured pooler host: {parsed.hostname}:{parsed.port} user={str(parsed.username)[:8]}…")
    probe_pg("pooler DSN", db_url)

    ref = urlparse(supabase_url).hostname.split(".")[0]
    direct = parsed._replace(
        netloc=f"postgres:{parsed.password}@db.{ref}.supabase.co:5432"
    )
    print(f"Derived direct host: db.{ref}.supabase.co:5432 user=postgres")
    probe_pg("direct DSN", direct.geturl())

    print("Project public endpoints (paused projects fail these):")
    probe_http("auth health", f"{supabase_url}/auth/v1/health")
    probe_http("rest root", f"{supabase_url}/rest/v1/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
