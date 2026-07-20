#!/usr/bin/env python3
"""Review manual requests and add lifetime AI credits.

The script uses the admin database connection and is dry-run by default.
There is deliberately no browser-accessible grant endpoint: users cannot grant
credits to themselves.

Examples:
    backend/.venv/bin/python backend/scripts/manage_credits.py --list
    backend/.venv/bin/python backend/scripts/manage_credits.py \
        --request-id <uuid> --amount 50 --apply
    backend/.venv/bin/python backend/scripts/manage_credits.py \
        --email adviser@example.com --amount 25 \
        --key promo-july-2026 --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import psycopg2  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402

from app.db import admin_database_url  # noqa: E402


def _default_credits() -> int:
    try:
        return max(0, int(os.environ.get("DEFAULT_LIFETIME_CREDITS", "50")))
    except ValueError:
        return 50


def _list_requests(cur) -> None:
    cur.execute(
        """
        SELECT r.id, r.status, r.created_at, r.message, r.principal_key,
               r.org_id, u.email
        FROM credit_requests r
        LEFT JOIN users u ON u.id = r.requested_by
        ORDER BY (r.status = 'pending') DESC, r.created_at DESC
        LIMIT 100
        """
    )
    rows = cur.fetchall()
    if not rows:
        print("No credit requests.")
        return
    for row in rows:
        print(
            f"{row['id']}  {row['status']:<8}  "
            f"{row.get('email') or row['principal_key']}  "
            f"{row['created_at'].isoformat()}\n"
            f"    {row.get('message') or '(no message)'}"
        )


def _resolve_target(cur, request_id: str | None, email: str | None) -> dict:
    if request_id:
        cur.execute(
            """
            SELECT r.id AS request_id, r.org_id, r.principal_key,
                   r.requested_by AS user_id, u.email
            FROM credit_requests r
            LEFT JOIN users u ON u.id = r.requested_by
            WHERE r.id = %s
            """,
            (request_id,),
        )
    else:
        cur.execute(
            """
            SELECT NULL::uuid AS request_id, m.org_id,
                   u.id::text AS principal_key, u.id AS user_id, u.email
            FROM users u
            JOIN org_memberships m ON m.user_id = u.id
            WHERE lower(u.email) = lower(%s)
            ORDER BY m.created_at
            LIMIT 1
            """,
            (email,),
        )
    row = cur.fetchone()
    if not row:
        raise SystemExit("No matching credit request or user.")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list recent credit requests")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--request-id", help="grant the account attached to a request")
    target.add_argument("--email", help="grant the account for this signed-in user")
    parser.add_argument("--amount", type=int, help="positive number of credits to add")
    parser.add_argument(
        "--key",
        help="stable idempotency key (required with --email; request ID is used otherwise)",
    )
    parser.add_argument("--note", default="Manual credit grant", help="ledger description")
    parser.add_argument("--apply", action="store_true", help="perform changes (default: dry run)")
    args = parser.parse_args()

    if not args.list and not (args.request_id or args.email):
        parser.error("choose --list, --request-id, or --email")
    if (args.request_id or args.email) and (args.amount is None or args.amount <= 0):
        parser.error("--amount must be a positive integer")
    if args.email and not args.key:
        parser.error("--key is required with --email to prevent duplicate grants")

    conn = psycopg2.connect(admin_database_url())
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if args.list:
            _list_requests(cur)
            conn.rollback()
            if not (args.request_id or args.email):
                return 0

        row = _resolve_target(cur, args.request_id, args.email)
        key = args.key or f"manual-request:{row['request_id']}"
        print(
            f"{'APPLY' if args.apply else 'DRY RUN'}: add {args.amount} credits "
            f"to {row.get('email') or row['principal_key']} "
            f"(org {row['org_id']}, key {key})"
        )
        if not args.apply:
            conn.rollback()
            return 0

        cur.execute("SELECT set_config('app.org_id', %s, true)", (str(row["org_id"]),))
        cur.execute(
            """
            SELECT * FROM grant_credits(
                %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            """,
            (
                row["org_id"],
                row["principal_key"],
                row["user_id"],
                args.amount,
                key,
                _default_credits(),
                json.dumps(
                    {
                        "source": "manual",
                        "description": args.note,
                        "request_id": (
                            str(row["request_id"]) if row["request_id"] else None
                        ),
                    }
                ),
            ),
        )
        account = cur.fetchone()
        if row["request_id"]:
            cur.execute(
                """
                UPDATE credit_requests
                SET status = 'approved', updated_at = now()
                WHERE id = %s AND status = 'pending'
                """,
                (row["request_id"],),
            )
        conn.commit()
        remaining = int(account["total_granted"]) - int(account["used"])
        print(f"Done. New lifetime balance: {remaining} credits.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
