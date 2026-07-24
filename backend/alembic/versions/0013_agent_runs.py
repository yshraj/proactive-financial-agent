"""Agent runtime tables: agent_runs + agent_steps.

An *agent run* is one durable execution of the LangGraph runtime (copilot
question, pre-meeting brief, …) processed by the worker via the existing
Postgres job queue (job kind ``agent_run``). Runs record their input/output
and a checkpoint of the last graph state; *steps* are the real, per-node
timeline that the frontend polls to replace the simulated thinking card —
plan, tool calls, synthesis, review — and double as the audit/replay trail.

Both tables are org-scoped with the standard RLS ``org_isolation`` policy;
the worker processes runs under ``system_context(job.org_id)`` exactly like
ingestion jobs, so every read/write here is tenant-bound.

Revision ID: 0013
Revises: 0012
"""
from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_UP = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id),
    user_id UUID,
    kind TEXT NOT NULL CHECK (kind IN ('copilot', 'brief')),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'DONE', 'ERROR')),
    input JSONB NOT NULL DEFAULT '{}'::jsonb,
    output JSONB,
    state JSONB,
    error TEXT,
    conversation_id UUID,
    client_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_org_time ON agent_runs(org_id, created_at DESC);

DROP TRIGGER IF EXISTS agent_runs_updated_at ON agent_runs;
CREATE TRIGGER agent_runs_updated_at
    BEFORE UPDATE ON agent_runs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS agent_steps (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id),
    seq INT NOT NULL,
    node TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING', 'DONE', 'ERROR')),
    detail JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run ON agent_steps(run_id, seq);

ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_steps ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS org_isolation ON agent_runs;
CREATE POLICY org_isolation ON agent_runs
    FOR ALL TO kritifin_app
    USING (org_id = app_org_id())
    WITH CHECK (org_id = app_org_id());

DROP POLICY IF EXISTS org_isolation ON agent_steps;
CREATE POLICY org_isolation ON agent_steps
    FOR ALL TO kritifin_app
    USING (org_id = app_org_id())
    WITH CHECK (org_id = app_org_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON agent_runs, agent_steps TO kritifin_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kritifin_app;
"""

_DOWN = """
DROP POLICY IF EXISTS org_isolation ON agent_steps;
DROP POLICY IF EXISTS org_isolation ON agent_runs;
DROP TABLE IF EXISTS agent_steps;
DROP TRIGGER IF EXISTS agent_runs_updated_at ON agent_runs;
DROP TABLE IF EXISTS agent_runs;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
