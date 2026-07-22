"""Add runnable_jobs_exist(): cheap existence probe for the worker drain.

The event-driven worker re-invokes itself when its time budget runs out with
work still queued. Without this probe it had to assume a backlog whenever the
budget floor was hit, costing one no-op invocation when the queue was in fact
empty. SECURITY DEFINER for the same reason as claim_next_job(): the worker
runs without a tenant context, and RLS would otherwise hide every row.

Revision ID: 0010
Revises: 0009
"""
from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_CREATE = """
CREATE OR REPLACE FUNCTION runnable_jobs_exist(p_stale_seconds int DEFAULT 600)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM jobs j
        WHERE j.status = 'PENDING'
           OR (j.status = 'PROCESSING'
               AND j.locked_at < NOW() - make_interval(secs => p_stale_seconds)
               AND j.attempts < j.max_attempts)
    );
$$;

REVOKE ALL ON FUNCTION runnable_jobs_exist(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION runnable_jobs_exist(int) TO kritifin_app;
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS runnable_jobs_exist(int);")
