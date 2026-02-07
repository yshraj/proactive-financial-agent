-- Run this in Supabase Dashboard → SQL Editor if you get:
--   relation "ingested_documents" does not exist
-- (e.g. you ran supabase_schema.sql before the ingestion table was added)

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
