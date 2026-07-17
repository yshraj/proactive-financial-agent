"""Alembic environment: raw-SQL migrations, URL from environment.

Migrations always run under the privileged role (DATABASE_ADMIN_URL, falling
back to DATABASE_URL) — the runtime ``kritifin_app`` role cannot ALTER tables.
"""
from __future__ import annotations

import os
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Load the project-root .env so local `alembic upgrade head` just works.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:  # pragma: no cover - dotenv is a runtime dependency
    pass

config = context.config

# No ORM metadata: migrations are hand-written SQL, autogenerate is unused.
target_metadata = None


def _database_url() -> str:
    url = (
        config.get_main_option("sqlalchemy.url")
        or os.environ.get("DATABASE_ADMIN_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        raise RuntimeError(
            "Set DATABASE_ADMIN_URL (preferred) or DATABASE_URL to run migrations."
        )
    # SQLAlchemy requires an explicit driver; psycopg2 is the app driver.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    try:
        from app.db import _force_ipv4  # DNS64/NAT64 stall mitigation

        url = _force_ipv4(url)
    except Exception:
        pass
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing (alembic upgrade head --sql)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
