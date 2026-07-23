"""Add runnable_jobs_count(): queue-depth metric for the worker drain.

Queue depth is the #1 scaling signal from the capacity roadmap (sustained
depth > ~10 is the agreed trigger for moving the job transport to SQS).
The drain logs it after each pass and a CloudWatch metric filter turns it
into KritiFin/QueueDepth. Same access model as runnable_jobs_exist()
(0010): SECURITY DEFINER because the worker runs without a tenant context
and RLS would otherwise hide every row.

Revision ID: 0011
Revises: 0010
"""
from __future__ import annotations

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_CREATE = """
CREATE OR REPLACE FUNCTION runnable_jobs_count(p_stale_seconds int DEFAULT 600)
RETURNS bigint
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT COUNT(*)
    FROM jobs j
    WHERE j.status = 'PENDING'
       OR (j.status = 'PROCESSING'
           AND j.locked_at < NOW() - make_interval(secs => p_stale_seconds)
           AND j.attempts < j.max_attempts);
$$;

REVOKE ALL ON FUNCTION runnable_jobs_count(int) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION runnable_jobs_count(int) TO kritifin_app;
"""


def upgrade() -> None:
    op.execute(_CREATE)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS runnable_jobs_count(int);")
