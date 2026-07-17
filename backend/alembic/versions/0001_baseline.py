"""Baseline: pre-tenancy schema (clients, alerts, ingested_documents).

Reproduces backend/supabase_schema.sql exactly (including migrations 001/002,
which the consolidated schema already contains). Idempotent (IF NOT EXISTS) so
existing databases can either run it as a no-op or be stamped:

    alembic stamp 0001   # database already has the legacy schema
    alembic upgrade head

Revision ID: 0001
Revises: None
"""
from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_UP = """
CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name TEXT,
    adviser_id UUID,
    retirement_target_age INT,
    risk_score INT CHECK (risk_score BETWEEN 1 AND 10),
    total_assets NUMERIC,
    cash_savings NUMERIC,
    last_review_date DATE,
    raw_profile_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    trigger_date DATE NOT NULL,
    type VARCHAR(50),
    priority VARCHAR(20),
    title TEXT,
    description TEXT,
    action_type VARCHAR(50),
    action_payload JSONB,
    status VARCHAR(20) DEFAULT 'PENDING',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_trigger_date ON alerts(trigger_date);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_client_id ON alerts(client_id);
CREATE INDEX IF NOT EXISTS idx_clients_adviser_id ON clients(adviser_id);
CREATE INDEX IF NOT EXISTS idx_clients_last_review ON clients(last_review_date);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS clients_updated_at ON clients;
CREATE TRIGGER clients_updated_at
    BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS alerts_updated_at ON alerts;
CREATE TRIGGER alerts_updated_at
    BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS ingested_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes BIGINT,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(content_hash)
);
CREATE INDEX IF NOT EXISTS idx_ingested_documents_content_hash ON ingested_documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_ingested_documents_uploaded_at ON ingested_documents(uploaded_at);
CREATE INDEX IF NOT EXISTS idx_ingested_documents_client_id ON ingested_documents(client_id);
"""

_DOWN = """
DROP TABLE IF EXISTS ingested_documents;
DROP TABLE IF EXISTS alerts;
DROP TABLE IF EXISTS clients;
DROP FUNCTION IF EXISTS set_updated_at();
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
