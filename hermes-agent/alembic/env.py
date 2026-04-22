"""Alembic migration environment for hermes-agent.

This env.py bridges Alembic with the existing SQLAlchemy models so that:
  - ``alembic upgrade head``   applies pending migrations
  - ``alembic revision --autogenerate -m "..."``  generates a new migration
    from the diff between the current models and the live database schema

Database URL resolution (first match wins):
  1. ``-x db_url=<url>`` CLI option
  2. ``DATABASE_URL`` environment variable
  3. SQLite fallback at ``$HERMES_HOME/state.db`` (for local/offline use)

Onboarding an existing database (already bootstrapped via create_all):
  alembic stamp head
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the hermes-agent package root is on sys.path so models are importable
# when alembic is invoked from any working directory.
_AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

# Import the metadata that owns all SQLAlchemy models.  The import also
# registers every mapped class so autogenerate can detect schema diffs.
from backend.db.base import Base  # noqa: E402
import backend.db.models  # noqa: E402, F401 — side-effect import registers all mappers

target_metadata = Base.metadata

# ── Alembic config object ───────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _get_database_url() -> str:
    """Resolve the database URL from CLI, env, or SQLite fallback."""
    # 1. -x db_url=...  CLI override
    x_url = context.get_x_argument(as_dictionary=True).get("db_url")
    if x_url:
        return x_url

    # 2. DATABASE_URL environment variable
    env_url = os.environ.get("DATABASE_URL", "").strip()
    if env_url:
        # Normalise to psycopg driver
        for src, dst in (
            ("postgresql://", "postgresql+psycopg://"),
            ("postgres://", "postgresql+psycopg://"),
        ):
            if env_url.startswith(src):
                return env_url.replace(src, dst, 1)
        return env_url

    # 3. Load .env from the agent root (development convenience)
    dotenv = _AGENT_ROOT / ".env"
    if dotenv.is_file():
        with dotenv.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        return _get_database_url()

    # 4. SQLite fallback
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    sqlite_path = hermes_home / "state.db"
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{sqlite_path}"


# ── Migration runners ───────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Run migrations in offline mode (no live DB connection).

    Emits SQL statements to stdout instead of executing them.
    Useful for generating a migration script to review or apply manually.
    """
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    url = _get_database_url()

    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # Render AS IDENTITY for PostgreSQL sequences on new tables
            render_as_batch=url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
