"""Rebuilding a room's table from its event log.

The log is the whole story: it starts from an empty table, every
transaction in it is concrete (each spawned piece's id, each piece moved),
and the table's one random source is seeded, so applying the events in
order reproduces the table at any moment. Nothing here knows an exercise.

A replay is read-only. It never writes to the room; it only reads events and
returns tables.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from sandbox.db.models import Event, Room, TableState
from sandbox.games.debrief import LogEvent
from sandbox.model import Ok, Operation, Table, TableRng, Transaction, run_op
from sandbox.model.entities import SYSTEM_SEAT
from sandbox.web.record import operation_classes

_CLASSES: dict[str, type] = operation_classes()
_ADAPTERS: dict[str, TypeAdapter[Any]] = {}


def load_events(session: Session, room: Room) -> list[LogEvent]:
    """Every event of ``room``, in order."""
    rows = session.execute(
        select(Event).where(Event.room_id == room.id).order_by(Event.seq)
    ).scalars()
    return [
        LogEvent(
            seq=row.seq,
            created_at=row.created_at,
            actor_seat=row.actor_seat,
            op_type=row.op_type,
            payload=dict(row.payload),
        )
        for row in rows
    ]


def seed_of(session: Session, room: Room) -> int:
    """The seed the room's table was created with."""
    state = session.get(TableState, room.id)
    if state is None:
        return 0
    rng: dict[str, Any] = state.snapshot["rng"]  # type: ignore[assignment]
    return int(rng["seed"])


def decode(op_type: str, payload: dict[str, Any]) -> Operation:
    """The operation a log entry records."""
    cls = _CLASSES.get(op_type)
    if cls is None:
        raise ValueError(f"The log names an operation {op_type!r} that is not known.")
    if cls is Transaction:
        steps = tuple(
            decode(step["op_type"], step["payload"]) for step in payload["steps"]
        )
        return Transaction(
            steps=steps,
            name=payload.get("name", ""),
            label=payload.get("label", ""),
            op_id=payload["op_id"],
            system=bool(payload.get("system", False)),
            activity_id=payload.get("activity_id", ""),
        )
    adapter = _ADAPTERS.setdefault(op_type, TypeAdapter(cls))
    operation: Operation = adapter.validate_python(payload)
    return operation


def steps_of(event: LogEvent) -> list[tuple[str, dict[str, Any]]]:
    """The leaf operations of ``event``: a transaction's steps, or the event itself."""
    if event.op_type != "Transaction":
        return [(event.op_type, event.payload)]
    return [(step["op_type"], step["payload"]) for step in event.payload["steps"]]


@dataclass
class Replayed:
    """A table rebuilt from the log, and how faithfully."""

    table: Table
    applied: int
    skipped: int
    last_seq: int


def replay(events: Sequence[LogEvent], seed: int, upto: int | None = None) -> Replayed:
    """The table after every event up to and including ``upto`` (all by default).

    An event the model now refuses is counted in ``skipped`` and passed over,
    so one bad row cannot stop the rest from being read.
    """
    table = Table(rng=TableRng(seed=seed))
    applied = skipped = 0
    last = 0
    for event in events:
        if upto is not None and event.seq > upto:
            break
        last = event.seq
        try:
            operation = decode(event.op_type, event.payload)
        except (ValueError, KeyError):
            skipped += 1
            continue
        actor = event.actor_seat or SYSTEM_SEAT
        if isinstance(run_op(table, actor, operation), Ok):
            applied += 1
        else:
            skipped += 1
    return Replayed(table=table, applied=applied, skipped=skipped, last_seq=last)


__all__ = [
    "LogEvent",
    "Replayed",
    "decode",
    "load_events",
    "replay",
    "seed_of",
    "steps_of",
]
