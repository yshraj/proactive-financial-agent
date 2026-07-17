"""
Shared test fixtures.

Integration tests run against a real PostgreSQL with the production schema:

- TEST_DATABASE_URL, when set (CI service container), is used directly;
- otherwise an embedded server is started via ``pgserver`` (pip installed,
  no Docker needed);
- Alembic migrations run as the admin role, then the app connects as the
  RLS-enforced ``kritifin_app`` role — the exact production configuration, so
  every integration test exercises row-level security for real.

Unit tests that never touch the DB simply don't request these fixtures.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Test environment defaults — set BEFORE app modules are imported anywhere.
# Empty strings block load_dotenv(override=False) from pulling real values in.
# ---------------------------------------------------------------------------
_TEST_JWT_SECRET = "test-jwt-secret-for-unit-tests-only"
os.environ.setdefault("SUPABASE_URL", "")
os.environ.setdefault("SUPABASE_JWT_SECRET", _TEST_JWT_SECRET)
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("QDRANT_URL", "")
os.environ.setdefault("QDRANT_API_KEY", "")
os.environ.setdefault("API_KEY", "")
os.environ.setdefault("SENTRY_DSN", "")
os.environ.setdefault("AUTH_MODE", "required")
os.environ.setdefault("ALLOW_DATA_RESET", "true")
os.environ.setdefault("INLINE_WORKER", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("DB_POOL_MAX", "5")
os.environ.setdefault("LOG_FORMAT", "text")
os.environ.setdefault("ENV", "test")

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

_ALL_DATA_TABLES = (
    "conversation_messages",
    "conversations",
    "jobs",
    "ai_outputs",
    "audit_log",
    "alerts",
    "ingested_documents",
    "clients",
    "org_memberships",
    "users",
    "organizations",
)


def _with_user(url: str, user: str) -> str:
    """Return the connection URL with a different role (trust-auth sockets)."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{user}@{host}{port}" if host else f"{user}@"
    return urlunparse(parsed._replace(netloc=netloc))


@pytest.fixture(scope="session")
def admin_db_url():
    """Admin (owner) connection URL to a disposable Postgres."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        yield explicit
        return
    pgserver = pytest.importorskip(
        "pgserver", reason="pgserver not installed and TEST_DATABASE_URL not set"
    )
    data_dir = tempfile.mkdtemp(prefix="kritifin-testpg-")
    server = pgserver.get_server(data_dir)
    try:
        yield server.get_uri()
    finally:
        server.cleanup()


@pytest.fixture(scope="session")
def migrated_db(admin_db_url):
    """Run all Alembic migrations, enable the runtime role, wire env vars."""
    import psycopg2
    from alembic import command
    from alembic.config import Config

    os.environ["DATABASE_ADMIN_URL"] = admin_db_url
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    driver_url = admin_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    cfg.set_main_option("sqlalchemy.url", driver_url)
    command.upgrade(cfg, "head")

    conn = psycopg2.connect(admin_db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("ALTER ROLE kritifin_app LOGIN")
        cur.execute("GRANT SELECT ON alembic_version TO kritifin_app")
    conn.close()

    app_url = _with_user(admin_db_url, "kritifin_app")
    os.environ["DATABASE_URL"] = app_url

    from app.db import close_pool

    close_pool()  # in case something opened a pool before the URL was set
    yield {"admin": admin_db_url, "app": app_url, "alembic_cfg": cfg}
    close_pool()


@pytest.fixture()
def clean_db(migrated_db):
    """Truncate all data tables and re-seed the default workspace."""
    import psycopg2

    conn = psycopg2.connect(migrated_db["admin"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(_ALL_DATA_TABLES)} CASCADE")
        cur.execute(
            "INSERT INTO organizations (id, name) VALUES (%s, 'Default Workspace') "
            "ON CONFLICT (id) DO NOTHING",
            (DEFAULT_ORG_ID,),
        )
    conn.close()

    from app import tenancy
    from app.services import cache

    tenancy.invalidate_cache()
    cache.clear_all_unscoped_for_tests()
    yield migrated_db


@pytest.fixture(autouse=True)
def _reset_context():
    """Never leak tenant/request context between tests."""
    from app.context import set_current_tenant, set_request_id

    set_current_tenant(None)
    set_request_id(None)
    yield
    set_current_tenant(None)
    set_request_id(None)


def _admin_conn(migrated):
    import psycopg2

    conn = psycopg2.connect(migrated["admin"])
    conn.autocommit = True
    return conn


def make_org(migrated, name: str = "Test Org"):
    """Create an org + owner user directly (admin), return a TenantContext."""
    from app.context import TenantContext

    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    conn = _admin_conn(migrated)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organizations (id, name) VALUES (%s, %s)", (org_id, name))
        cur.execute(
            "INSERT INTO users (id, email) VALUES (%s, %s)",
            (user_id, f"{user_id[:8]}@example.test"),
        )
        cur.execute(
            "INSERT INTO org_memberships (org_id, user_id, role) VALUES (%s, %s, 'owner')",
            (org_id, user_id),
        )
    conn.close()
    return TenantContext(org_id=org_id, user_id=user_id, role="owner")


@pytest.fixture()
def org_a(clean_db):
    return make_org(clean_db, "Org A")


@pytest.fixture()
def org_b(clean_db):
    return make_org(clean_db, "Org B")


@pytest.fixture()
def bind_org_a(org_a):
    """Bind org A as the ambient tenant (like a request would)."""
    from app.context import set_current_tenant

    set_current_tenant(org_a)
    yield org_a
    set_current_tenant(None)


def make_jwt(user_id: str, email: str = "adviser@example.test") -> str:
    """Mint an HS256 Supabase-shaped access token for tests."""
    import jwt

    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "aud": "authenticated",
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        _TEST_JWT_SECRET,
        algorithm="HS256",
    )


def auth_headers_for(ctx) -> dict:
    return {"Authorization": f"Bearer {make_jwt(ctx.user_id)}"}


@pytest.fixture(scope="session")
def api_app(migrated_db):
    """The FastAPI app, imported only after the test env/DB are ready."""
    from app.main import app

    return app


@pytest.fixture()
def api_client(api_app, clean_db):
    from fastapi.testclient import TestClient

    with TestClient(api_app, raise_server_exceptions=False) as client:
        yield client


def seed_client(migrated, org_id: str, full_name: str = "Alan Partridge", **fields):
    """Insert a client row directly (admin) and return its id."""
    conn = _admin_conn(migrated)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO clients (org_id, full_name, risk_score, total_assets, last_review_date)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                org_id,
                full_name,
                fields.get("risk_score", 5),
                fields.get("total_assets", 250000),
                fields.get("last_review_date"),
            ),
        )
        client_id = str(cur.fetchone()[0])
        for alert in fields.get("alerts", []):
            cur.execute(
                """
                INSERT INTO alerts (org_id, client_id, trigger_date, type, priority, title, status)
                VALUES (%s, %s, %s::date, %s, %s, %s, %s)
                """,
                (
                    org_id,
                    client_id,
                    alert.get("trigger_date"),
                    alert.get("type", "DEADLINE"),
                    alert.get("priority", "HIGH"),
                    alert.get("title", "Test alert"),
                    alert.get("status", "PENDING"),
                ),
            )
    conn.close()
    return client_id
