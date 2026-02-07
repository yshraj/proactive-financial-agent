-- =============================================================================
-- Proactive Financial Agent – Supabase (PostgreSQL) Schema
-- Run this in Supabase Dashboard → SQL Editor → New query → Run
-- =============================================================================

-- Table: clients (the "hard" facts per client)
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

-- Table: alerts (the proactive engine – ingestion populates this)
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    trigger_date DATE NOT NULL,
    type VARCHAR(50),   -- 'DEADLINE', 'OPPORTUNITY', 'COMPLIANCE'
    priority VARCHAR(20), -- 'HIGH', 'MEDIUM', 'LOW'
    title TEXT,
    description TEXT,
    action_type VARCHAR(50), -- 'EMAIL_DRAFT', 'Meeting_Link'
    action_payload JSONB,
    status VARCHAR(20) DEFAULT 'PENDING',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for the monitor/pulse query (alerts by date range)
CREATE INDEX IF NOT EXISTS idx_alerts_trigger_date ON alerts(trigger_date);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_client_id ON alerts(client_id);

-- Optional: index for filtering clients by adviser
CREATE INDEX IF NOT EXISTS idx_clients_adviser_id ON clients(adviser_id);
CREATE INDEX IF NOT EXISTS idx_clients_last_review ON clients(last_review_date);

-- Optional: trigger to keep updated_at in sync (Supabase supports this)
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

-- =============================================================================
-- Ingestion: stored PDF metadata (content hash for duplicate detection)
-- =============================================================================
CREATE TABLE IF NOT EXISTS ingested_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes BIGINT,
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(content_hash)
);
CREATE INDEX IF NOT EXISTS idx_ingested_documents_content_hash ON ingested_documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_ingested_documents_uploaded_at ON ingested_documents(uploaded_at);
