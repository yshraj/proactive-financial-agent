"""Content-level duplicate detection: text_hash on ingested_documents.

Byte-level UNIQUE(org_id, content_hash) cannot catch the same document
uploaded in two formats (e.g. the .md and .pdf of one fact-find), which
previously created duplicate clients and alerts. ``text_hash`` stores the
SHA-256 of the whitespace-normalised extracted text so ingestion can detect
same-content documents after extraction and link instead of duplicating.

Nullable: legacy rows and documents whose extraction failed have no hash.
Not unique: the lookup is advisory (ingestion decides), and NULLs are common.

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ingested_documents ADD COLUMN IF NOT EXISTS text_hash VARCHAR(64);
        CREATE INDEX IF NOT EXISTS idx_ingested_documents_org_text_hash
            ON ingested_documents(org_id, text_hash) WHERE text_hash IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_ingested_documents_org_text_hash;
        ALTER TABLE ingested_documents DROP COLUMN IF EXISTS text_hash;
        """
    )
