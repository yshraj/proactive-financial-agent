#!/usr/bin/env python3
"""
One-off cleanup for duplicate clients created before ingestion learned to
merge by name (same document uploaded in two formats produced two identical
clients, each with their own alerts).

Per organization, clients are grouped by whitespace-normalised, case-folded
full_name. The oldest row in each group is kept; alerts and documents from the
newer duplicates are repointed to it; duplicate PENDING alerts (same type +
title + trigger_date) are removed; the emptied client rows are deleted.
"Unknown Client" groups are never merged (distinct unknown people).

Usage (defaults to a dry run):
    backend/.venv/bin/python backend/scripts/dedupe_clients.py            # report only
    backend/.venv/bin/python backend/scripts/dedupe_clients.py --apply    # perform

Runs on DATABASE_ADMIN_URL (falls back to DATABASE_URL) so it can see and fix
every workspace.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import psycopg2  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402

from app.db import admin_database_url  # noqa: E402


def normalise(name: str) -> str:
    return " ".join((name or "").split()).lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform changes (default: dry run)")
    args = parser.parse_args()

    conn = psycopg2.connect(admin_database_url())
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        "SELECT id, org_id, full_name, created_at FROM clients ORDER BY org_id, created_at"
    )
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in cur.fetchall():
        key = (str(row["org_id"]), normalise(row["full_name"]))
        if key[1] and key[1] != "unknown client":
            groups[key].append(row)

    merged_groups = 0
    removed_clients = 0
    removed_alerts = 0
    for (org_id, name), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        keeper, duplicates = rows[0], rows[1:]
        dup_ids = [str(r["id"]) for r in duplicates]
        print(f"[{org_id}] '{name}': keeping {keeper['id']}, merging {len(dup_ids)} duplicate(s)")
        merged_groups += 1
        removed_clients += len(dup_ids)

        # Repoint alerts and documents from duplicates to the keeper.
        cur.execute(
            "UPDATE alerts SET client_id = %s WHERE client_id = ANY(%s::uuid[])",
            (keeper["id"], dup_ids),
        )
        cur.execute(
            "UPDATE ingested_documents SET client_id = %s WHERE client_id = ANY(%s::uuid[])",
            (keeper["id"], dup_ids),
        )

        # Remove now-duplicated PENDING alerts (keep the oldest of each identity).
        cur.execute(
            """
            DELETE FROM alerts a
            USING alerts b
            WHERE a.client_id = %s AND b.client_id = %s
              AND a.status = 'PENDING' AND b.status = 'PENDING'
              AND a.type = b.type
              AND COALESCE(a.title, '') = COALESCE(b.title, '')
              AND a.trigger_date = b.trigger_date
              AND a.created_at > b.created_at
            """,
            (keeper["id"], keeper["id"]),
        )
        removed_alerts += cur.rowcount or 0

        cur.execute("DELETE FROM clients WHERE id = ANY(%s::uuid[])", (dup_ids,))

    print(
        f"\n{merged_groups} duplicate group(s); {removed_clients} client row(s) "
        f"and {removed_alerts} duplicate alert(s) {'removed' if args.apply else 'WOULD be removed'}."
    )
    if args.apply:
        conn.commit()
        print("Applied.")
    else:
        conn.rollback()
        print("Dry run — re-run with --apply to perform. (Vectors for merged "
              "clients keep their original client_id; re-ingest or clear data "
              "if per-client RAG scoping matters for the merged records.)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
