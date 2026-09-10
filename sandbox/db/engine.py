"""Database engine and session factory.

One process-wide engine, built from ``DATABASE_URL``. Local development and
tests fall back to a SQLite file so nothing extra needs to be running;
production sets ``DATABASE_URL`` to a Postgres DSN. Nothing here is
FastAPI-specific - ``sandbox.web`` wires ``session_scope`` into routes.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from sandbox.db.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_URL = f"sqlite:///{PROJECT_ROOT / 'ethics-sandbox.db'}"


def database_url() -> str:
    """The configured database URL, defaulting to a local SQLite file."""
    return os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)


def make_engine(url: str | None = None) -> Engine:
    """Build an engine for ``url`` (or the configured database)."""
    resolved = url if url is not None else database_url()
    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    return create_engine(resolved, connect_args=connect_args)


engine: Engine = make_engine()
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False
)


def init_db(target: Engine | None = None) -> None:
    """Create every table that does not exist yet.

    Convenient for local SQLite development and for tests. Production runs
    on Postgres and is migrated with Alembic (``sandbox/db/migrations``)
    instead; this call is additive and never destructive, so running it
    against an already-migrated database is harmless.
    """
    Base.metadata.create_all(target or engine)


@contextmanager
def session_scope(factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    """A session that commits on a clean exit and rolls back on an exception."""
    session = (factory or SessionLocal)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "DEFAULT_SQLITE_URL",
    "SessionLocal",
    "database_url",
    "engine",
    "init_db",
    "make_engine",
    "session_scope",
]
