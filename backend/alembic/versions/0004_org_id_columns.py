"""Add org_id to domain tables, backfill to the default workspace, constrain.

Expand-and-backfill in one revision (safe at current data volumes):
1. add nullable ``org_id`` columns,
2. backfill every existing row to the default workspace,
3. SET NOT NULL + FK + composite indexes,
4. replace the global ``UNIQUE(content_hash)`` with ``UNIQUE(org_id,
   content_hash)`` — duplicate detection must not be a cross-tenant oracle.

``alerts.org_id`` is deliberately denormalized (also derivable via client_id)
so RLS stays one-hop and hot-path indexes stay simple.

Revision ID: 0004
Revises: 0003
"""
from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

_UP = f"""
ALTER TABLE clients ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS org_id UUID;
ALTER TABLE ingested_documents ADD COLUMN IF NOT EXISTS org_id UUID;

UPDATE clients SET org_id = '{DEFAULT_ORG_ID}' WHERE org_id IS NULL;
UPDATE alerts SET org_id = '{DEFAULT_ORG_ID}' WHERE org_id IS NULL;
UPDATE ingested_documents SET org_id = '{DEFAULT_ORG_ID}' WHERE org_id IS NULL;

ALTER TABLE clients ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE alerts ALTER COLUMN org_id SET NOT NULL;
ALTER TABLE ingested_documents ALTER COLUMN org_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_clients_org') THEN
        ALTER TABLE clients
            ADD CONSTRAINT fk_clients_org FOREIGN KEY (org_id) REFERENCES organizations(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_alerts_org') THEN
        ALTER TABLE alerts
            ADD CONSTRAINT fk_alerts_org FOREIGN KEY (org_id) REFERENCES organizations(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ingested_documents_org') THEN
        ALTER TABLE ingested_documents
            ADD CONSTRAINT fk_ingested_documents_org FOREIGN KEY (org_id) REFERENCES organizations(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_clients_org_last_review ON clients(org_id, last_review_date);
CREATE INDEX IF NOT EXISTS idx_alerts_org_status_date ON alerts(org_id, status, trigger_date);
CREATE INDEX IF NOT EXISTS idx_alerts_org_client ON alerts(org_id, client_id);
CREATE INDEX IF NOT EXISTS idx_ingested_documents_org_uploaded
    ON ingested_documents(org_id, uploaded_at DESC);

-- Per-org duplicate detection: drop the global uniqueness on content_hash.
ALTER TABLE ingested_documents
    DROP CONSTRAINT IF EXISTS ingested_documents_content_hash_key;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_ingested_documents_org_hash') THEN
        ALTER TABLE ingested_documents
            ADD CONSTRAINT uq_ingested_documents_org_hash UNIQUE (org_id, content_hash);
    END IF;
END $$;
"""

_DOWN = """
ALTER TABLE ingested_documents DROP CONSTRAINT IF EXISTS uq_ingested_documents_org_hash;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ingested_documents_content_hash_key') THEN
        ALTER TABLE ingested_documents
            ADD CONSTRAINT ingested_documents_content_hash_key UNIQUE (content_hash);
    END IF;
END $$;

DROP INDEX IF EXISTS idx_ingested_documents_org_uploaded;
DROP INDEX IF EXISTS idx_alerts_org_client;
DROP INDEX IF EXISTS idx_alerts_org_status_date;
DROP INDEX IF EXISTS idx_clients_org_last_review;

ALTER TABLE ingested_documents DROP COLUMN IF EXISTS org_id;
ALTER TABLE alerts DROP COLUMN IF EXISTS org_id;
ALTER TABLE clients DROP COLUMN IF EXISTS org_id;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
