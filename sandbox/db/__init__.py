"""Database package: SQLAlchemy models, the engine, and migrations.

``sandbox.web.rooms`` is the only code outside this package that should
import a database session; everything else works through that service
layer.
"""

from sandbox.db.engine import SessionLocal, database_url, engine, init_db, session_scope
from sandbox.db.models import Base, Event, Participant, Reflection, Room, TableState

__all__ = [
    "Base",
    "Event",
    "Participant",
    "Reflection",
    "Room",
    "SessionLocal",
    "TableState",
    "database_url",
    "engine",
    "init_db",
    "session_scope",
]
