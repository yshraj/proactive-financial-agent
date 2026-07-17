"""
Tenant-isolation proofs (the release gate for multi-tenancy).

Three independent layers are exercised against a real migrated Postgres with
the runtime role:

1. RLS-only: raw SQL as ``kritifin_app`` WITHOUT any WHERE clause — policies
   alone must hide other tenants' rows (this is the "app forgot its WHERE"
   drill from the RFC).
2. GUC binding: db.get_cursor with an org context can only see that org.
3. Provisioning: first login claims the default workspace; later users get
   isolated personal workspaces; lookups are cached.
"""
from __future__ import annotations

import uuid

import psycopg2
import pytest

from app.context import DEFAULT_ORG_ID
from app.db import get_cursor
from tests.conftest import seed_client


def _app_conn(db):
    conn = psycopg2.connect(db["app"])
    conn.autocommit = False
    return conn


def test_rls_denies_everything_without_org_guc(clean_db, org_a):
    """No app.org_id bound -> the runtime role sees zero tenant rows."""
    seed_client(clean_db, org_a.org_id)
    conn = _app_conn(clean_db)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM clients")  # deliberately no WHERE
            assert cur.fetchone()[0] == 0
    finally:
        conn.rollback()
        conn.close()


def test_rls_hides_other_org_even_without_where_clause(clean_db, org_a, org_b):
    """The 'stripped WHERE clause' drill: policies alone isolate tenants."""
    seed_client(clean_db, org_a.org_id, "Org A Client")
    seed_client(clean_db, org_b.org_id, "Org B Client")

    conn = _app_conn(clean_db)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.org_id', %s, true)", (org_a.org_id,))
            cur.execute("SELECT full_name FROM clients")  # no WHERE at all
            names = [r[0] for r in cur.fetchall()]
        assert names == ["Org A Client"]
    finally:
        conn.rollback()
        conn.close()


def test_rls_blocks_cross_org_insert(clean_db, org_a, org_b):
    """WITH CHECK: writing a row stamped with another org must fail."""
    conn = _app_conn(clean_db)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.org_id', %s, true)", (org_a.org_id,))
            with pytest.raises(psycopg2.Error):
                cur.execute(
                    "INSERT INTO clients (org_id, full_name) VALUES (%s, 'Smuggled')",
                    (org_b.org_id,),
                )
    finally:
        conn.rollback()
        conn.close()


def test_rls_blocks_cross_org_update_and_delete(clean_db, org_a, org_b):
    victim = seed_client(clean_db, org_b.org_id, "Victim")
    conn = _app_conn(clean_db)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.org_id', %s, true)", (org_a.org_id,))
            cur.execute("UPDATE clients SET full_name = 'Defaced' WHERE id = %s", (victim,))
            assert cur.rowcount == 0
            cur.execute("DELETE FROM clients WHERE id = %s", (victim,))
            assert cur.rowcount == 0
    finally:
        conn.rollback()
        conn.close()


def test_get_cursor_binds_org_guc(clean_db, org_a, org_b):
    seed_client(clean_db, org_a.org_id, "A1")
    seed_client(clean_db, org_b.org_id, "B1")
    with get_cursor(ctx=org_a) as cur:
        cur.execute("SELECT full_name FROM clients")
        assert [r["full_name"] for r in cur.fetchall()] == ["A1"]
    with get_cursor(ctx=org_b) as cur:
        cur.execute("SELECT full_name FROM clients")
        assert [r["full_name"] for r in cur.fetchall()] == ["B1"]


def test_guc_does_not_leak_between_transactions(clean_db, org_a):
    """set_config(..., is_local=true) must vanish at transaction end — the
    property that makes this design safe behind a transaction pooler."""
    seed_client(clean_db, org_a.org_id)
    with get_cursor(ctx=org_a) as cur:
        cur.execute("SELECT COUNT(*) AS n FROM clients")
        assert cur.fetchone()["n"] == 1
    # Same pool, new transaction, no ctx: the GUC must be gone.
    with get_cursor() as cur:
        cur.execute("SELECT current_setting('app.org_id', true) AS org")
        value = cur.fetchone()["org"]
        assert value in (None, "")


def test_membership_bootstrap_policies(clean_db, org_a, org_b):
    """With only app.user_id bound, a user sees exactly their own rows."""
    conn = _app_conn(clean_db)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.user_id', %s, true)", (org_a.user_id,))
            cur.execute("SELECT id FROM users")
            assert [str(r[0]) for r in cur.fetchall()] == [org_a.user_id]
            cur.execute("SELECT org_id FROM org_memberships")
            assert [str(r[0]) for r in cur.fetchall()] == [org_a.org_id]
    finally:
        conn.rollback()
        conn.close()


# ---------------------------------------------------------------------------
# JIT provisioning
# ---------------------------------------------------------------------------


def test_first_user_claims_default_workspace(clean_db):
    from app import tenancy

    user_id = str(uuid.uuid4())
    ctx = tenancy.resolve_tenant(user_id=user_id, email="first@firm.co.uk")
    assert ctx.org_id == DEFAULT_ORG_ID
    assert ctx.role == "owner"


def test_second_user_gets_personal_workspace(clean_db):
    from app import tenancy

    first = tenancy.resolve_tenant(user_id=str(uuid.uuid4()), email="first@firm.co.uk")
    second = tenancy.resolve_tenant(user_id=str(uuid.uuid4()), email="second@other.co.uk")
    assert second.org_id != first.org_id
    assert second.role == "owner"


def test_provisioning_is_idempotent_and_cached(clean_db):
    from app import tenancy

    user_id = str(uuid.uuid4())
    a = tenancy.resolve_tenant(user_id=user_id, email="x@y.z")
    b = tenancy.resolve_tenant(user_id=user_id, email="x@y.z")
    assert a.org_id == b.org_id
    # And with the cache invalidated, the DB still returns the same workspace.
    tenancy.invalidate_cache(user_id)
    c = tenancy.resolve_tenant(user_id=user_id, email="x@y.z")
    assert c.org_id == a.org_id


def test_existing_member_keeps_their_workspace(clean_db, org_a):
    from app import tenancy

    ctx = tenancy.resolve_tenant(user_id=org_a.user_id, email="member@firm.co.uk")
    assert ctx.org_id == org_a.org_id


# ---------------------------------------------------------------------------
# Cache scoping
# ---------------------------------------------------------------------------


def test_cache_keys_are_org_prefixed(org_a, org_b):
    from app.services import cache

    cache.set_scoped("pulse:2026-07-17", {"total": 1}, 60, ctx=org_a)
    assert cache.get_scoped("pulse:2026-07-17", ctx=org_a) == {"total": 1}
    assert cache.get_scoped("pulse:2026-07-17", ctx=org_b) is None


def test_scoped_cache_requires_context():
    from app.services import cache

    with pytest.raises(RuntimeError):
        cache.get_scoped("brief:x")


def test_org_invalidation_does_not_touch_other_org(org_a, org_b):
    from app.services import cache

    cache.set_scoped("digest:v:today", "A digest", 60, ctx=org_a)
    cache.set_scoped("digest:v:today", "B digest", 60, ctx=org_b)
    cache.invalidate_all_ai_caches(ctx=org_a)
    assert cache.get_scoped("digest:v:today", ctx=org_a) is None
    assert cache.get_scoped("digest:v:today", ctx=org_b) == "B digest"


def test_vector_search_requires_org_id():
    from app.services.rag_context import search_qdrant

    with pytest.raises(ValueError, match="org_id"):
        search_qdrant([0.0] * 4, org_id="")


def test_vector_upsert_requires_tenant():
    from app.services.vector_store import upsert_to_qdrant

    with pytest.raises(RuntimeError):
        upsert_to_qdrant(["chunk"], [[0.0] * 4], client_id="c1")  # no ctx bound
