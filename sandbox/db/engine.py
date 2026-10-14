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
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from sandbox.db.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_URL = f"sqlite:///{PROJECT_ROOT / 'ethics-sandbox.db'}"


def database_url() -> str:
    """The configured database URL, defaulting to a local SQLite file."""
    return os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)


def _queue_sqlite_writers(engine: Engine) -> None:
    """Make SQLite transactions wait their turn instead of failing.

    By default a SQLite transaction starts as a reader and becomes a writer
    at its first write. Two that both read and then both write cannot both
    become writers, and SQLite answers "database is locked" at once, without
    waiting. A live room saving its table while someone joins it is exactly
    that. ``BEGIN IMMEDIATE`` takes the write lock when the transaction
    starts, so a second one waits (up to the driver's timeout) for the first
    to finish rather than failing. Postgres needs none of this.
    """

    @event.listens_for(engine, "connect")
    def _no_driver_begin(dbapi_connection: Any, _record: Any) -> None:
        # Let SQLAlchemy say when a transaction begins, not the driver.
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")


def make_engine(url: str | None = None) -> Engine:
    """Build an engine for ``url`` (or the configured database)."""
    resolved = url if url is not None else database_url()
    if not resolved.startswith("sqlite"):
        return create_engine(resolved)
    engine = create_engine(resolved, connect_args={"check_same_thread": False})
    _queue_sqlite_writers(engine)
    return engine


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
