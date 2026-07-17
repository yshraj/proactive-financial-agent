"""
Backfill org_id onto existing Qdrant points (one-time tenancy migration).

Scrolls the whole collection and stamps every point missing an org_id payload
field with the default workspace id (which is where all pre-tenancy Postgres
rows were backfilled by Alembic revision 0004). Also creates the payload
indexes required for fast filtered search.

Run from repo root after `alembic upgrade head`:

    python backend/scripts/backfill_qdrant_org.py [--org-id UUID] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Load .env from project root and make the app package importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
env_path = Path(__file__).resolve().parents[2] / ".env"
if env_path.exists():
    from dotenv import load_dotenv

    load_dotenv(env_path)

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
BATCH = 256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org-id", default=os.environ.get("BACKFILL_ORG_ID", DEFAULT_ORG_ID))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from qdrant_client.models import (
        Filter,
        IsEmptyCondition,
        PayloadField,
    )

    from app.services.clients import get_qdrant_client
    from app.services.config import QDRANT_COLLECTION
    from app.services.vector_store import ensure_payload_indexes

    client = get_qdrant_client()
    if not client.collection_exists(QDRANT_COLLECTION):
        print(f"Collection '{QDRANT_COLLECTION}' does not exist — nothing to backfill.")
        return 0

    missing_org = Filter(
        must=[IsEmptyCondition(is_empty=PayloadField(key="org_id"))]
    )

    total = 0
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=missing_org,
            limit=BATCH,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        if not points:
            break
        ids = [p.id for p in points]
        total += len(ids)
        if args.dry_run:
            print(f"[dry-run] would stamp {len(ids)} points")
        else:
            client.set_payload(
                collection_name=QDRANT_COLLECTION,
                payload={"org_id": args.org_id},
                points=ids,
            )
            print(f"Stamped {len(ids)} points (running total {total})")
        if offset is None:
            break

    if not args.dry_run:
        ensure_payload_indexes(QDRANT_COLLECTION)
        print("Payload indexes ensured (org_id keyword/is_tenant, client_id keyword).")
    print(f"Done. {total} point(s) {'needed' if args.dry_run else 'received'} org_id={args.org_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
