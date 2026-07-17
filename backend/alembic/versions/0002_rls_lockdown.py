"""Day-1 lockdown: enable row-level security on all existing tables.

With RLS enabled and no policies defined, non-owner roles are denied by
default. On Supabase this immediately closes the auto-generated PostgREST
Data API (`anon` / `authenticated` roles) which could otherwise read these
tables with only the public anon key. The backend, connecting as the table
owner, is unaffected until policies + FORCE land in revision 0006.

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_TABLES = ("clients", "alerts", "ingested_documents")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
