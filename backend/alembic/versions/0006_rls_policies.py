"""RLS enforcement: kritifin_app runtime role, org policies, JIT provisioning.

Design (production-readiness RFC, D2):

- The API connects as ``kritifin_app`` (NOBYPASSRLS, least privilege). Every
  transaction binds ``app.user_id`` / ``app.org_id`` GUCs via
  ``set_config(..., true)`` (see app/db.py); policies key on those.
- Tables use ENABLE (not FORCE) row level security: the table owner
  (``postgres``) intentionally bypasses policies and remains the documented
  break-glass + migrations path. The runtime role is not the owner, so RLS
  fully applies to it — and to Supabase's PostgREST roles.
- ``provision_user_workspace()`` is SECURITY DEFINER so first-login
  provisioning can write users/organizations/org_memberships without granting
  the runtime role broad rights on those tables.

The role is created NOLOGIN with no password; enable it per environment with:
    ALTER ROLE kritifin_app LOGIN PASSWORD '<from secret manager>';
then point DATABASE_URL at kritifin_app and keep DATABASE_ADMIN_URL on postgres
for Alembic. Rollback lever: point DATABASE_URL back at the owner role.

Revision ID: 0006
Revises: 0005
"""
from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

# Tables with a direct org_id column and full org-scoped DML for the app role.
_ORG_TABLES = (
    "clients",
    "alerts",
    "ingested_documents",
    "ai_outputs",
    "jobs",
    "conversations",
    "conversation_messages",
)

_UP = f"""
-- ---------------------------------------------------------------------------
-- GUC helper functions (empty string -> NULL so unset GUCs deny, not error)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION app_org_id() RETURNS uuid
LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.org_id', true), '')::uuid $$;

CREATE OR REPLACE FUNCTION app_user_id() RETURNS uuid
LANGUAGE sql STABLE AS
$$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$;

-- ---------------------------------------------------------------------------
-- Runtime role (login enabled out-of-band; see migration docstring)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kritifin_app') THEN
        CREATE ROLE kritifin_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO kritifin_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
    clients, alerts, ingested_documents, ai_outputs, jobs,
    conversations, conversation_messages
TO kritifin_app;
-- The legal audit record is append-only for the runtime role.
GRANT SELECT, INSERT ON audit_log TO kritifin_app;
REVOKE UPDATE, DELETE ON audit_log FROM kritifin_app;
-- Read-only tenancy visibility; writes go through the SECURITY DEFINER function.
GRANT SELECT ON organizations, users, org_memberships TO kritifin_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kritifin_app;
-- Readiness reporting reads the migration version.
GRANT SELECT ON alembic_version TO kritifin_app;

-- ---------------------------------------------------------------------------
-- Enable RLS everywhere (owner bypass retained as break-glass; no FORCE)
-- ---------------------------------------------------------------------------
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE org_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
{chr(10).join(f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;' for t in _ORG_TABLES)}

-- ---------------------------------------------------------------------------
-- Org-scoped policies for domain tables
-- ---------------------------------------------------------------------------
{chr(10).join(
    f'''DROP POLICY IF EXISTS org_isolation ON {t};
CREATE POLICY org_isolation ON {t}
    FOR ALL TO kritifin_app
    USING (org_id = app_org_id())
    WITH CHECK (org_id = app_org_id());'''
    for t in _ORG_TABLES
)}

-- audit_log: append + read within the org; no UPDATE/DELETE policy exists
-- (and the 0005 trigger blocks mutation even for the owner).
DROP POLICY IF EXISTS audit_insert ON audit_log;
CREATE POLICY audit_insert ON audit_log
    FOR INSERT TO kritifin_app
    WITH CHECK (org_id = app_org_id());
DROP POLICY IF EXISTS audit_select ON audit_log;
CREATE POLICY audit_select ON audit_log
    FOR SELECT TO kritifin_app
    USING (org_id = app_org_id());

-- Bootstrap policies: before app.org_id exists, a request may only see itself.
DROP POLICY IF EXISTS users_self ON users;
CREATE POLICY users_self ON users
    FOR SELECT TO kritifin_app
    USING (id = app_user_id());

DROP POLICY IF EXISTS memberships_visible ON org_memberships;
CREATE POLICY memberships_visible ON org_memberships
    FOR SELECT TO kritifin_app
    USING (user_id = app_user_id() OR org_id = app_org_id());

DROP POLICY IF EXISTS organizations_own ON organizations;
CREATE POLICY organizations_own ON organizations
    FOR SELECT TO kritifin_app
    USING (id = app_org_id());

-- ---------------------------------------------------------------------------
-- JIT workspace provisioning (SECURITY DEFINER, owner = migration role)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION provision_user_workspace(p_user_id uuid, p_email text)
RETURNS TABLE (out_org_id uuid, out_role text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_default CONSTANT uuid := '{DEFAULT_ORG_ID}';
    v_org uuid;
    v_role text;
BEGIN
    INSERT INTO users (id, email, last_seen_at)
    VALUES (p_user_id, COALESCE(p_email, ''), NOW())
    ON CONFLICT (id) DO UPDATE
        SET email = CASE WHEN EXCLUDED.email <> '' THEN EXCLUDED.email ELSE users.email END,
            last_seen_at = NOW();

    SELECT m.org_id, m.role INTO v_org, v_role
    FROM org_memberships m
    WHERE m.user_id = p_user_id
    ORDER BY m.created_at
    LIMIT 1;
    IF FOUND THEN
        out_org_id := v_org; out_role := v_role;
        RETURN NEXT; RETURN;
    END IF;

    -- First-ever user claims the default workspace (holds pre-tenancy data).
    IF NOT EXISTS (SELECT 1 FROM org_memberships WHERE org_id = v_default) THEN
        PERFORM 1 FROM organizations WHERE id = v_default FOR UPDATE;
        -- Re-check both conditions under the lock (racing first logins).
        SELECT m.org_id, m.role INTO v_org, v_role
        FROM org_memberships m WHERE m.user_id = p_user_id
        ORDER BY m.created_at LIMIT 1;
        IF FOUND THEN
            out_org_id := v_org; out_role := v_role;
            RETURN NEXT; RETURN;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM org_memberships WHERE org_id = v_default) THEN
            INSERT INTO org_memberships (org_id, user_id, role)
            VALUES (v_default, p_user_id, 'owner');
            out_org_id := v_default; out_role := 'owner';
            RETURN NEXT; RETURN;
        END IF;
    END IF;

    -- Everyone after the first user gets a personal workspace.
    INSERT INTO organizations (name)
    VALUES (COALESCE(NULLIF(p_email, ''), 'Workspace'))
    RETURNING id INTO v_org;
    INSERT INTO org_memberships (org_id, user_id, role)
    VALUES (v_org, p_user_id, 'owner');
    out_org_id := v_org; out_role := 'owner';
    RETURN NEXT;
END;
$$;

REVOKE ALL ON FUNCTION provision_user_workspace(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION provision_user_workspace(uuid, text) TO kritifin_app;

-- ---------------------------------------------------------------------------
-- Job-queue claim/sweep (SECURITY DEFINER: the worker claims across orgs,
-- then processes each job under that org's tenant context)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION claim_next_job(p_worker text, p_stale_seconds int DEFAULT 600)
RETURNS SETOF jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    WITH candidate AS (
        SELECT j.id
        FROM jobs j
        WHERE j.status = 'PENDING'
           OR (j.status = 'PROCESSING'
               AND j.locked_at < NOW() - make_interval(secs => p_stale_seconds)
               AND j.attempts < j.max_attempts)
        ORDER BY j.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE jobs j
    SET status = 'PROCESSING',
        locked_at = NOW(),
        locked_by = p_worker,
        attempts = j.attempts + 1,
        message = 'Processing…'
    FROM candidate
    WHERE j.id = candidate.id
    RETURNING j.*;
END;
$$;

CREATE OR REPLACE FUNCTION fail_exhausted_jobs(p_stale_seconds int DEFAULT 600)
RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_count int;
BEGIN
    UPDATE jobs
    SET status = 'ERROR',
        message = 'Failed',
        error = COALESCE(error, 'Worker retries exhausted (process restarted mid-job).')
    WHERE status = 'PROCESSING'
      AND locked_at < NOW() - make_interval(secs => p_stale_seconds)
      AND attempts >= max_attempts;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION claim_next_job(text, int) FROM PUBLIC;
REVOKE ALL ON FUNCTION fail_exhausted_jobs(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_next_job(text, int) TO kritifin_app;
GRANT EXECUTE ON FUNCTION fail_exhausted_jobs(int) TO kritifin_app;

-- ---------------------------------------------------------------------------
-- Supabase PostgREST roles: explicit deny (belt and braces alongside RLS)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
    END IF;
END $$;
"""

_DOWN = f"""
DROP FUNCTION IF EXISTS claim_next_job(text, int);
DROP FUNCTION IF EXISTS fail_exhausted_jobs(int);
DROP FUNCTION IF EXISTS provision_user_workspace(uuid, text);
{chr(10).join(f'DROP POLICY IF EXISTS org_isolation ON {t};' for t in _ORG_TABLES)}
DROP POLICY IF EXISTS audit_insert ON audit_log;
DROP POLICY IF EXISTS audit_select ON audit_log;
DROP POLICY IF EXISTS users_self ON users;
DROP POLICY IF EXISTS memberships_visible ON org_memberships;
DROP POLICY IF EXISTS organizations_own ON organizations;
ALTER TABLE organizations DISABLE ROW LEVEL SECURITY;
ALTER TABLE users DISABLE ROW LEVEL SECURITY;
ALTER TABLE org_memberships DISABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log DISABLE ROW LEVEL SECURITY;
{chr(10).join(f'ALTER TABLE {t} DISABLE ROW LEVEL SECURITY;' for t in _ORG_TABLES if t not in ('clients', 'alerts', 'ingested_documents'))}
-- clients/alerts/ingested_documents keep RLS enabled (0002 lockdown).
DROP FUNCTION IF EXISTS app_org_id();
DROP FUNCTION IF EXISTS app_user_id();
-- The kritifin_app role is left in place (dropping roles is a manual op).
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
