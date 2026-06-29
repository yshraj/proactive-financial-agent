-- Link ingested documents to the client they were extracted into, so the
-- Client 360 page can show an accurate document count.
-- Run this in Supabase Dashboard -> SQL Editor.
-- ON DELETE SET NULL keeps document rows if a client is removed.

ALTER TABLE ingested_documents
    ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_ingested_documents_client_id
    ON ingested_documents(client_id);
