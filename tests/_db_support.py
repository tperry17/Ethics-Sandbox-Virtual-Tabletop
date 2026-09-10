"""A fresh, in-memory database for tests that touch persistence.

Every test gets its own engine and schema rather than sharing the
development SQLite file, so tests can run in any order, in parallel, and
without leaving files behind.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from sandbox.db.models import Base


def make_test_engine() -> Engine:
    """A fresh in-memory SQLite engine with the full schema created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@contextmanager
def db_session() -> Iterator[Session]:
    """A session against a fresh in-memory database, closed on exit."""
    engine = make_test_engine()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
