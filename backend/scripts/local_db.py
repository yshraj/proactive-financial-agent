#!/usr/bin/env python3
"""
Start (or reuse) the embedded local PostgreSQL for development and print its
connection URI. Used when no reachable DATABASE_URL is configured (e.g. the
Supabase dev project is paused).

    backend/.venv/bin/python backend/scripts/local_db.py

The server runs in backend/.localdb (gitignored) and persists until the
machine restarts; re-running this script restarts it if needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pgserver

DATA_DIR = Path(__file__).resolve().parents[1] / ".localdb"


def main() -> int:
    db = pgserver.get_server(DATA_DIR, cleanup_mode=None)
    print(db.get_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
