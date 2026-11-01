"""Dependencies shared by the web application and its routers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from sandbox.db import session_scope


def get_session() -> Iterator[Session]:
    """One request-scoped database session, committed or rolled back for you.

    Routes that take one are plain ``def``, not ``async def``: FastAPI runs
    them on a worker thread, so a query waiting on SQLite's write lock waits
    there, not on the event loop that the lock's holder needs to finish.
    """
    with session_scope() as session:
        yield session
