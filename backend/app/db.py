"""
PostgreSQL connection for the backend.
Uses DATABASE_URL from environment (e.g. Supabase connection string).
Connections are pooled to avoid per-query TLS handshake overhead.
"""
from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from urllib.parse import parse_qs, urlparse

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

_pool: ThreadedConnectionPool | None = None


def _force_ipv4(url: str) -> str:
    """Pin the DSN to the host's IPv4 address via ``hostaddr``.

    On networks with DNS64/NAT64 the host resolves to synthesized ``64:ff9b::``
    IPv6 addresses that libpq tries first; when IPv6 can't route, each connect
    stalls ~15-75s before falling back to IPv4. Resolving IPv4 ourselves and
    passing it as ``hostaddr`` (while keeping ``host`` for TLS/cert validation)
    avoids that stall. Best-effort: on any failure we return the URL unchanged.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host or "hostaddr" in parse_qs(parsed.query):
            return url
        ipv4 = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        sep = "&" if parsed.query else "?"
        return f"{url}{sep}hostaddr={ipv4}"
    except Exception:
        return url


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = ThreadedConnectionPool(minconn=2, maxconn=20, dsn=_force_ipv4(url))
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
