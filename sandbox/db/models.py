"""SQLAlchemy 2.0 models for rooms, participants, table state, and the event log.

This module owns storage shape only. It knows nothing about tabletop rules -
those live in ``sandbox.model`` - and nothing about exercises - those live in
``sandbox.games``. ``sandbox.web.rooms`` is the only code that should import
a database session alongside the model package.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Plain JSON is portable to SQLite; on Postgres the same column stores as
# JSONB, which is what "SQLAlchemy with Postgres in production and SQLite
# locally" implies for anything schemaless like a table snapshot or an
# event payload.
JSONColumn = JSON().with_variant(JSONB(), "postgresql")


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for every table in the sandbox database."""


class Room(Base):
    """One table, from creation to closure.

    ``code`` is the short, unambiguous string a facilitator shares to invite
    people in; ``id`` is the stable internal identity everything else keys
    on, so ``code`` can be reused for a new room only after all rows keyed by
    the old room's id are gone.
    """

    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    code: Mapped[str] = mapped_column(unique=True, index=True)
    game_slug: Mapped[str]
    status: Mapped[str] = mapped_column(default="open")
    config: Mapped[dict[str, object]] = mapped_column(JSONColumn, default=dict)
    facilitator_participant_id: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    last_active_at: Mapped[datetime] = mapped_column(default=_now)
    closed_at: Mapped[datetime | None] = mapped_column(default=None)

    participants: Mapped[list[Participant]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
    table_state: Mapped[TableState | None] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
    events: Mapped[list[Event]] = relationship(
        back_populates="room", cascade="all, delete-orphan", order_by="Event.seq"
    )
    reflections: Mapped[list[Reflection]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )


class Participant(Base):
    """One browser's presence in one room.

    ``cookie_id`` is the value carried in the signed, http-only identity
    cookie described in CLAUDE.md. It is how the same browser returning to
    the same room reclaims its seat and its hand - there is no other
    identity system.
    """

    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("room_id", "cookie_id"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    cookie_id: Mapped[str] = mapped_column(index=True)
    display_name: Mapped[str]
    seat_id: Mapped[str | None] = mapped_column(default=None)
    is_observer: Mapped[bool] = mapped_column(default=False)
    connected: Mapped[bool] = mapped_column(default=False)
    last_seen_at: Mapped[datetime] = mapped_column(default=_now)

    room: Mapped[Room] = relationship(back_populates="participants")


class TableState(Base):
    """The latest snapshot of a room's tabletop.

    One row per room. ``version`` mirrors ``Table.version`` at the moment of
    the snapshot, so a late joiner can tell whether replaying the events
    after it is worth doing or whether the snapshot alone is current.
    """

    __tablename__ = "table_states"

    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), primary_key=True)
    version: Mapped[int]
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONColumn)
    updated_at: Mapped[datetime] = mapped_column(default=_now)

    room: Mapped[Room] = relationship(back_populates="table_state")


class Event(Base):
    """One entry in a room's append-only history.

    Never update or delete a row here: it is the record of what happened,
    and session replay, the debrief, and the exports all read it as ground
    truth. ``seq`` is a per-room counter assigned by the caller under the
    room's own serialization (see ``sandbox.web.rooms.apply_op``), not the
    autoincrementing primary key, which only orders rows within the table.
    """

    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("room_id", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    seq: Mapped[int]
    actor_seat: Mapped[str | None] = mapped_column(default=None)
    op_type: Mapped[str]
    payload: Mapped[dict[str, object]] = mapped_column(JSONColumn, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    room: Mapped[Room] = relationship(back_populates="events")


class Reflection(Base):
    """One participant's answer to a facilitation prompt."""

    __tablename__ = "reflections"

    id: Mapped[str] = mapped_column(primary_key=True, default=_new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"))
    prompt_key: Mapped[str]
    body: Mapped[str]
    visibility: Mapped[str] = mapped_column(default="private")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    room: Mapped[Room] = relationship(back_populates="reflections")


__all__ = [
    "Base",
    "Event",
    "Participant",
    "Reflection",
    "Room",
    "TableState",
]
