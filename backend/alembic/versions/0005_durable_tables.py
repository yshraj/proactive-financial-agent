"""Durable stores: audit_log (append-only), ai_outputs, jobs, conversations.

- ``audit_log`` is the append-only legal record (who/what/when/where/before/
  after + request correlation). A trigger blocks UPDATE/DELETE; the runtime
  role additionally gets INSERT/SELECT only (revision 0006).
- ``ai_outputs`` is the mutable human-review register that powers the existing
  approve UI; approvals also write an ``ai.output.approved`` audit event.
- ``jobs`` backs the Postgres queue (FOR UPDATE SKIP LOCKED claims).
- ``conversations`` / ``conversation_messages`` make chat threads durable and
  user-owned (closes the unowned-conversation hijack).

Revision ID: 0005
Revises: 0004
"""
from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_UP = """
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id),
    actor_user_id UUID,
    actor_type TEXT NOT NULL DEFAULT 'user'
        CHECK (actor_type IN ('user', 'system', 'ai', 'service', 'demo')),
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    client_id UUID,
    request_id TEXT,
    ip INET,
    user_agent TEXT,
    model TEXT,
    prompt_version TEXT,
    before JSONB,
    after JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_org_time ON audit_log(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_org_action ON audit_log(org_id, action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_request ON audit_log(request_id);

CREATE OR REPLACE FUNCTION audit_log_block_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = 'insufficient_privilege',
        MESSAGE = 'audit_log is append-only: ' || TG_OP || ' blocked';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log;
CREATE TRIGGER audit_log_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_block_mutation();

CREATE TABLE IF NOT EXISTS ai_outputs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id),
    kind TEXT NOT NULL,
    client_id UUID,
    client_name TEXT,
    model TEXT,
    prompt_version TEXT,
    preview TEXT NOT NULL DEFAULT '',
    ai_generated BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID,
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_outputs_org_time ON ai_outputs(org_id, created_at DESC);

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id),
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'ERROR')),
    filename TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    progress INT NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT 'Queued',
    document_id UUID,
    error TEXT,
    attempts INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(status, created_at)
    WHERE status IN ('PENDING', 'PROCESSING');
CREATE INDEX IF NOT EXISTS idx_jobs_org_time ON jobs(org_id, created_at DESC);

DROP TRIGGER IF EXISTS jobs_updated_at ON jobs;
CREATE TRIGGER jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id),
    user_id UUID,
    client_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conversations_org_user ON conversations(org_id, user_id, updated_at DESC);

DROP TRIGGER IF EXISTS conversations_updated_at ON conversations;
CREATE TRIGGER conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS conversation_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_conv
    ON conversation_messages(conversation_id, id);
"""

_DOWN = """
DROP TABLE IF EXISTS conversation_messages;
DROP TABLE IF EXISTS conversations;
DROP TABLE IF EXISTS jobs;
DROP TABLE IF EXISTS ai_outputs;
DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log;
DROP TABLE IF EXISTS audit_log;
DROP FUNCTION IF EXISTS audit_log_block_mutation();
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
