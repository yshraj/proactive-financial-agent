"""
PostgreSQL connection for the backend.

Uses DATABASE_URL from environment (e.g. Supabase connection string).
Connections are pooled to avoid per-query TLS handshake overhead.

Tenant scoping: every cursor opened while a tenant context is bound (see
app.context) starts its transaction with ``set_config('app.user_id'|'app.org_id',
..., true)``. Row-level-security policies key on those GUCs, so even a query
that forgets its ``WHERE org_id = %s`` clause cannot cross a tenant boundary.
``set_config(..., is_local := true)`` is transaction-scoped, which makes it safe
behind Supabase's transaction-mode pooler (no GUC leakage between clients).
"""
from __future__ import annotations

import os
import socket
import time
from contextlib import contextmanager
from typing import Optional
from urllib.parse import parse_qs, urlparse

from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from app.context import TenantContext, get_current_tenant

_pool: Optional[ThreadedConnectionPool] = None

# Validate (SELECT 1) a pooled connection that sat idle longer than this
# before handing it out. On AWS Lambda the process is frozen between
# invocations and the pooler may drop the TCP connection in the meantime;
# recently-used connections skip the ping, so steady traffic pays nothing.
_IDLE_PING_SECONDS = float(os.environ.get("DB_IDLE_PING_SECONDS", "30"))

# Last-used clock per pooled connection, keyed by id() — psycopg2 connections
# are C objects that reject new attributes. Invariant: an entry exists only
# while its connection is alive inside the pool (stamped at creation and
# check-in, popped on every discard, cleared with the pool), so ids cannot be
# recycled into stale entries. A connection with no entry is brand new.
_last_used: dict[int, float] = {}


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


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def admin_database_url() -> str:
    """Privileged connection string for migrations and break-glass operations.

    Falls back to DATABASE_URL so single-role deployments keep working; once the
    runtime is cut over to the ``kritifin_app`` role, set DATABASE_ADMIN_URL to
    the owner (postgres) connection string for Alembic.
    """
    return os.environ.get("DATABASE_ADMIN_URL") or database_url()


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        maxconn = int(os.environ.get("DB_POOL_MAX", "20"))
        minconn = min(int(os.environ.get("DB_POOL_MIN", "2")), maxconn)
        _pool = ThreadedConnectionPool(
            minconn=minconn, maxconn=maxconn, dsn=_force_ipv4(database_url())
        )
        # Stamp the minconn connections created eagerly above so they age like
        # any other (psycopg2 keeps them in the private ready list; the
        # attribute has been stable across psycopg2 2.x).
        now = time.monotonic()
        for conn in getattr(_pool, "_pool", []):
            _last_used[id(conn)] = now
    return _pool


def close_pool() -> None:
    """Close all pooled connections (lifespan shutdown / test teardown)."""
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        finally:
            _pool = None
            _last_used.clear()


def _discard(pool: ThreadedConnectionPool, conn) -> None:
    """Close and forget a dead/stale connection."""
    _last_used.pop(id(conn), None)
    pool.putconn(conn, close=True)


def _checkout(pool: ThreadedConnectionPool):
    """Get a healthy connection from the pool, discarding stale ones.

    Freshly created and recently used connections are returned as-is; ones
    that sat idle past the ping window are validated first. A dead connection
    (e.g. dropped while a Lambda execution environment was frozen, or after a
    database restart) is closed and replaced instead of surfacing as an
    OperationalError inside a request or job.
    """
    for _ in range(pool.maxconn + 1):
        conn = pool.getconn()
        if conn.closed:  # non-zero also covers psycopg2's "broken" state
            _discard(pool, conn)
            continue
        last = _last_used.get(id(conn))
        if last is None:
            # No entry = created by the pool during this getconn(): brand new
            # connection, nothing to validate.
            return conn
        if time.monotonic() - last < _IDLE_PING_SECONDS:
            return conn
        try:
            with conn.cursor() as ping:
                ping.execute("SELECT 1")
            # End the ping transaction so tenant GUCs open a fresh one.
            conn.rollback()
            return conn
        except Exception:
            _discard(pool, conn)
    return pool.getconn()  # last resort; errors surface at first use


def _checkin(pool: ThreadedConnectionPool, conn) -> None:
    _last_used[id(conn)] = time.monotonic()
    pool.putconn(conn)


def get_connection():
    """Return a pooled connection. Prefer get_cursor() for automatic cleanup."""
    return _checkout(_get_pool())


def _bind_tenant_guc(cur, ctx: TenantContext) -> None:
    """Set transaction-local GUCs that RLS policies key on.

    Must be the first statements of the transaction. ``set_config`` (rather than
    ``SET LOCAL``) so the values are passed as ordinary query parameters. An
    empty org_id (bootstrap/provisioning context) sets only app.user_id.
    """
    if ctx.org_id:
        cur.execute("SELECT set_config('app.org_id', %s, true)", (ctx.org_id,))
    if ctx.user_id:
        cur.execute("SELECT set_config('app.user_id', %s, true)", (ctx.user_id,))


@contextmanager
def get_cursor(commit: bool = False, *, ctx: Optional[TenantContext] = None):
    """Yield a RealDictCursor inside a tenant-bound transaction.

    ``ctx`` defaults to the request/job tenant bound in app.context. Cursors
    opened with no tenant anywhere (health checks, bootstrap) set no GUCs — RLS
    then denies all tenant-scoped rows by default.
    """
    tenant = ctx or get_current_tenant()
    pool = _get_pool()
    conn = _checkout(pool)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if tenant is not None:
                _bind_tenant_guc(cur, tenant)
            yield cur
            if commit:
                conn.commit()
            else:
                conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        _checkin(pool, conn)
