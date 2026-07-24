#!/usr/bin/env python3
"""
Re-index ingested documents into the current embedding provider's Qdrant
collection (the fastembed migration tool).

Replays every stored document for an org: fetch original from storage →
re-extract text → chunk → embed with the CONFIGURED provider (fastembed by
default) → upsert into the provider's collection. The legacy collection is
left untouched, so this is safe to run before flipping traffic and can be
re-run at any time (chunks are re-upserted with fresh point ids; run
--purge-first to drop the org's points in the target collection first).

Usage (from backend/, with DATABASE_URL/QDRANT_URL/storage env configured):

    python scripts/reindex_embeddings.py --org 00000000-0000-0000-0000-000000000001
    python scripts/reindex_embeddings.py --org <uuid> --dry-run
    python scripts/reindex_embeddings.py --org <uuid> --purge-first
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR.parent / ".env", override=False)
except ImportError:  # pragma: no cover
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="organization (workspace) UUID")
    parser.add_argument("--dry-run", action="store_true", help="list what would be indexed")
    parser.add_argument("--purge-first", action="store_true",
                        help="delete the org's points in the target collection first")
    args = parser.parse_args()

    from app.context import set_current_tenant, system_context
    from app.db import get_cursor
    from app.services import embeddings, storage
    from app.services.config import QDRANT_COLLECTION
    from app.services.llm_extractor import extract_text_from_bytes
    from app.services.vector_store import (
        delete_org_points,
        ensure_collection,
        index_document_text,
    )

    ctx = system_context(args.org, request_id="reindex")
    set_current_tenant(ctx)

    print(f"Embedding provider: {embeddings.provider()} ({embeddings.model_name()}, "
          f"{embeddings.vector_size()} dims)")
    print(f"Target collection:  {QDRANT_COLLECTION}")

    with get_cursor(ctx=ctx) as cur:
        cur.execute(
            """
            SELECT d.id, d.filename, d.file_path, d.client_id, d.uploaded_at,
                   c.full_name AS client_name
            FROM ingested_documents d
            LEFT JOIN clients c ON c.id = d.client_id
            WHERE d.org_id = %s
            ORDER BY d.uploaded_at
            """,
            (args.org,),
        )
        docs = cur.fetchall()

    print(f"Documents to re-index: {len(docs)}")
    if args.dry_run:
        for d in docs:
            print(f"  - {d['filename']} (client={d.get('client_name') or 'unlinked'})")
        return 0
    if not docs:
        print("Nothing to do.")
        return 0

    ensure_collection()
    if args.purge_first:
        print(f"Purging org points from {QDRANT_COLLECTION}…")
        delete_org_points(args.org)

    indexed = skipped = 0
    for d in docs:
        name = d["filename"] or str(d["id"])
        file_path = d.get("file_path") or ""
        if not file_path:
            print(f"  SKIP {name}: no stored original")
            skipped += 1
            continue
        try:
            content = storage.fetch_document(file_path)
            ext = "." + (name.rsplit(".", 1)[-1].lower() if "." in name else "pdf")
            text = extract_text_from_bytes(content, ext, name)
            index_document_text(
                text,
                client_id=str(d.get("client_id") or ""),
                client_name=(d.get("client_name") or "Unknown").strip(),
                doc_type="Document",
                doc_date=str(d.get("uploaded_at") or "")[:10] or None,
                document_id=str(d["id"]),
                filename=name,
                source_type=ext.lstrip("."),
                ingested_at=str(d.get("uploaded_at") or ""),
            )
            indexed += 1
            print(f"  OK   {name}")
        except Exception as exc:  # noqa: BLE001 - keep going; report at the end
            skipped += 1
            print(f"  FAIL {name}: {type(exc).__name__}")

    print(f"\nDone: {indexed} indexed, {skipped} skipped/failed.")
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
