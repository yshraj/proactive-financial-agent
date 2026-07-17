"""Tenancy model: organizations, users, org_memberships + default workspace.

An organization IS the tenant (one level — see the production-readiness RFC,
decision D1). ``users.id`` equals the Supabase ``auth.users.id`` (JWT sub).
The fixed default workspace holds pre-tenancy data (backfilled in 0004) and
the AUTH_MODE=demo shared workspace; the first real user to sign in claims it.

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

_UP = f"""
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS organizations_updated_at ON organizations;
CREATE TRIGGER organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,             -- equals Supabase auth.users.id (JWT sub)
    email TEXT NOT NULL DEFAULT '',
    full_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS org_memberships (
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('owner', 'adviser')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (org_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_org_memberships_user ON org_memberships(user_id);

INSERT INTO organizations (id, name)
VALUES ('{DEFAULT_ORG_ID}', 'Default Workspace')
ON CONFLICT (id) DO NOTHING;
"""

_DOWN = """
DROP TABLE IF EXISTS org_memberships;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS organizations;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
