"""
PostgreSQL connection for the backend.
Uses DATABASE_URL from environment (e.g. Supabase connection string).
Connections are pooled to avoid per-query TLS handshake overhead.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = ThreadedConnectionPool(minconn=2, maxconn=20, dsn=url)
    return _pool


def get_connection():
    """Return a pooled connection. Prefer get_cursor() for automatic cleanup."""
    return _get_pool().getconn()


@contextmanager
def get_cursor(commit=False):
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
            if commit:
                conn.commit()
            else:
                conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
