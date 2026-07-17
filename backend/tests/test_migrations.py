"""Migration discipline: downgrade one step and re-upgrade must both work."""
from __future__ import annotations

from alembic import command
from alembic.script import ScriptDirectory


def test_schema_matches_head(migrated_db):
    import psycopg2

    conn = psycopg2.connect(migrated_db["admin"])
    with conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        current = cur.fetchone()[0]
    conn.close()
    script = ScriptDirectory.from_config(migrated_db["alembic_cfg"])
    assert current == script.get_current_head()


def test_downgrade_one_and_reupgrade(migrated_db):
    """The last revision (RLS/policies) must be cleanly reversible."""
    cfg = migrated_db["alembic_cfg"]
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")

    # Sanity: the app role still works against the re-upgraded schema.
    import psycopg2

    conn = psycopg2.connect(migrated_db["app"])
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.org_id', %s, true)",
                    ("00000000-0000-0000-0000-000000000001",))
        cur.execute("SELECT COUNT(*) FROM clients")
        cur.fetchone()
    conn.rollback()
    conn.close()


def test_all_tables_have_rls_enabled(migrated_db):
    """Every application table must carry row-level security."""
    import psycopg2

    expected = {
        "clients", "alerts", "ingested_documents", "organizations", "users",
        "org_memberships", "audit_log", "ai_outputs", "jobs",
        "conversations", "conversation_messages",
    }
    conn = psycopg2.connect(migrated_db["admin"])
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' AND rowsecurity = true
            """
        )
        with_rls = {r[0] for r in cur.fetchall()}
    conn.close()
    missing = expected - with_rls
    assert not missing, f"tables without RLS: {missing}"
