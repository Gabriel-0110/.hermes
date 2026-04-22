"""SQLAlchemy session management for Hermes shared storage."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from hermes_constants import get_hermes_home

_ENGINE_CACHE: dict[str, Engine] = {}
_SESSION_FACTORY_CACHE: dict[str, sessionmaker[Session]] = {}


def get_database_url() -> str | None:
    value = os.getenv("DATABASE_URL", "").strip()
    return normalize_database_url(value) if value else None


def get_sqlite_fallback_url(db_path: Path | None = None) -> str:
    target = db_path or (get_hermes_home() / "state.db")
    target.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{target}"


def normalize_database_url(database_url: str | None) -> str | None:
    """Prefer the installed psycopg driver when a generic Postgres URL is provided."""

    if database_url is None:
        return None

    normalized = database_url.strip()
    if not normalized:
        return None

    if normalized.startswith("postgresql://"):
        return normalized.replace("postgresql://", "postgresql+psycopg://", 1)
    if normalized.startswith("postgres://"):
        return normalized.replace("postgres://", "postgresql+psycopg://", 1)
    return normalized


def get_database_backend(database_url: str | None = None) -> str:
    url = normalize_database_url(database_url) if database_url is not None else get_database_url()
    if not url:
        return "sqlite_fallback"
    if url.startswith("postgresql"):
        return "timescaledb"
    if url.startswith("sqlite"):
        return "sqlite_fallback"
    return "sqlalchemy_other"


def _build_engine(database_url: str) -> Engine:
    database_url = normalize_database_url(database_url) or get_sqlite_fallback_url()
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30
    return create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def get_engine(*, database_url: str | None = None, db_path: Path | None = None) -> Engine:
    resolved_url = normalize_database_url(database_url) or get_database_url() or get_sqlite_fallback_url(db_path)
    engine = _ENGINE_CACHE.get(resolved_url)
    if engine is None:
        engine = _build_engine(resolved_url)
        _ENGINE_CACHE[resolved_url] = engine
    return engine


def get_session_factory(*, database_url: str | None = None, db_path: Path | None = None) -> sessionmaker[Session]:
    resolved_url = normalize_database_url(database_url) or get_database_url() or get_sqlite_fallback_url(db_path)
    factory = _SESSION_FACTORY_CACHE.get(resolved_url)
    if factory is None:
        factory = sessionmaker(
            bind=get_engine(database_url=resolved_url),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )
        _SESSION_FACTORY_CACHE[resolved_url] = factory
    return factory


@contextmanager
def session_scope(*, database_url: str | None = None, db_path: Path | None = None) -> Iterator[Session]:
    session = get_session_factory(database_url=database_url, db_path=db_path)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
