"""Room lifecycle: creating tables, joining them, seating people, and the
one write path into a table's state.

This is the service layer between the FastAPI routes and both the database
(``sandbox.db``) and the pure tabletop model (``sandbox.model``). No
exercise-specific logic belongs here - seat and observer handling is
generic room administration, not a rule of any particular game. What a
room's table holds, how its seats are named and how many there may be
come from the exercise's game definition, read through
``sandbox.games.engine``; an exercise without one gets plain seats at an
empty table.
"""

from __future__ import annotations

import dataclasses
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sandbox.db.models import Event, Participant, Room, TableState
from sandbox.db.snapshot import from_snapshot, to_snapshot
from sandbox.games import GAMES, Game, playable_slugs
from sandbox.games.engine import build_seat, build_table
from sandbox.model import (
    Ok,
    Operation,
    OpOutcome,
    Reject,
    Seat,
    Table,
    TableRng,
    Transaction,
    run_op,
)

# Excludes characters easily confused when read aloud or handwritten:
# I, O, 0, 1, L.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6

# CLAUDE.md: facilitators run groups of 4-30 participants. An exercise's
# game definition sets its own bound (``meta.players.max``), and a room's
# config may override either (``config["max_seats"]``).
DEFAULT_MAX_SEATS = 30

DEFAULT_DISPLAY_NAME = "Participant"


class RoomError(Exception):
    """Base class for problems joining or acting in a room."""


class RoomNotFoundError(RoomError):
    """No room exists with the given code."""


class RoomClosedError(RoomError):
    """The room exists but is no longer accepting activity."""


class SeatUnavailableError(RoomError):
    """The requested seat cannot be claimed right now."""


class UnknownExerciseError(RoomError):
    """The requested game slug has no matching exercise definition."""


def _now() -> datetime:
    return datetime.now(UTC)


# -- lookups ------------------------------------------------------------------


def get_room(session: Session, room_id: str) -> Room | None:
    """The room with this internal id, if it exists."""
    return session.get(Room, room_id)


def get_room_by_code(session: Session, code: str) -> Room | None:
    """The room with this room code, if it exists. Codes are case-insensitive."""
    normalised = code.strip().upper()
    stmt = select(Room).where(Room.code == normalised)
    return session.execute(stmt).scalar_one_or_none()


def get_participant(
    session: Session, room_id: str, cookie_id: str
) -> Participant | None:
    """The participant this browser is, in this room, if it has joined before."""
    stmt = select(Participant).where(
        Participant.room_id == room_id, Participant.cookie_id == cookie_id
    )
    return session.execute(stmt).scalar_one_or_none()


def game_for(room: Room) -> Game | None:
    """The game definition this room's table is built from, if it has one."""
    return GAMES.get(room.game_slug)


def max_seats(room: Room) -> int:
    """How many seats this room may grow to hold."""
    configured = room.config.get("max_seats")
    if isinstance(configured, int):
        return configured
    game = game_for(room)
    if game is not None:
        return game.definition.meta.players.max
    return DEFAULT_MAX_SEATS


# -- table persistence ---------------------------------------------------


def load_table(session: Session, room: Room) -> Table:
    """The room's current tabletop, or a fresh, empty one if it has none yet."""
    state = session.get(TableState, room.id)
    if state is None:
        return Table()
    return from_snapshot(state.snapshot)


def save_table_state(session: Session, room: Room, table: Table) -> None:
    """Persist ``table`` as the room's latest snapshot."""
    state = session.get(TableState, room.id)
    snapshot = to_snapshot(table)
    if state is None:
        session.add(
            TableState(room_id=room.id, version=table.version, snapshot=snapshot)
        )
        return
    state.version = table.version
    state.snapshot = snapshot
    state.updated_at = _now()


def save_live_table_state(session: Session, room: Room, table: Table) -> None:
    """Persist a live room's table, keeping what the room service owns.

    Who sits where is the room service's to change (``join_room``,
    ``claim_seat``, ``release_seat`` and the rest), and it writes those
    changes to the stored table, not to the live one. So a live room's
    snapshot keeps the stored seats it has not heard of yet, with the zones
    they own, and every stored seat's occupant, rather than writing back
    its own older copy over them.
    """
    state = session.get(TableState, room.id)
    snapshot = to_snapshot(table)
    if state is not None:
        seats = snapshot["seats"]
        zones = snapshot["zones"]
        stored_seats = state.snapshot.get("seats")
        stored_zones = state.snapshot.get("zones")
        assert isinstance(seats, dict) and isinstance(zones, dict)
        assert isinstance(stored_seats, dict) and isinstance(stored_zones, dict)
        for seat_id, seat in stored_seats.items():
            if seat_id in seats:
                live_seat = seats[seat_id]
                if isinstance(live_seat, dict) and isinstance(seat, dict):
                    live_seat["participant_id"] = seat.get("participant_id")
                continue
            seats[seat_id] = seat
            for zone_id, zone in stored_zones.items():
                if isinstance(zone, dict) and zone.get("owner_seat") == seat_id:
                    zones.setdefault(zone_id, zone)
        state.version = table.version
        state.snapshot = snapshot
        state.updated_at = _now()
        return
    session.add(TableState(room_id=room.id, version=table.version, snapshot=snapshot))


# -- room and seat lifecycle -----------------------------------------------


def generate_room_code(session: Session) -> str:
    """A room code not already in use, from the unambiguous alphabet."""
    for _ in range(50):
        candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if get_room_by_code(session, candidate) is None:
            return candidate
    raise RuntimeError("Could not find an unused room code after 50 attempts.")


def _dedupe_name(
    session: Session,
    room_id: str,
    display_name: str,
    *,
    exclude_participant_id: str | None = None,
) -> str:
    """``display_name``, or a distinguishable variant if it is already taken."""
    base = display_name.strip() or DEFAULT_DISPLAY_NAME
    stmt = select(Participant.display_name).where(Participant.room_id == room_id)
    if exclude_participant_id is not None:
        stmt = stmt.where(Participant.id != exclude_participant_id)
    taken = set(session.execute(stmt).scalars().all())
    if base not in taken:
        return base
    suffix = 2
    while f"{base} ({suffix})" in taken:
        suffix += 1
    return f"{base} ({suffix})"


def _find_free_seat(table: Table) -> Seat | None:
    return next(
        (seat for seat in table.seats.values() if seat.participant_id is None), None
    )


def _apply_and_log(
    session: Session, room: Room, table: Table, seat_id: str, transaction: Transaction
) -> None:
    """Apply a transaction the room service built, and log it as one event."""
    outcome = run_op(table, seat_id, transaction)
    if not isinstance(outcome, Ok):
        raise RuntimeError(f"{transaction.label} was refused: {outcome.reason}")
    append_event(session, room, actor_seat=seat_id, op=transaction)


def create_room(
    session: Session,
    *,
    game_slug: str,
    facilitator_cookie_id: str,
    facilitator_name: str,
    config: dict[str, object] | None = None,
) -> tuple[Room, Participant]:
    """Start a new room for ``game_slug``, seating its facilitator.

    The table is built from the exercise's game definition - its zones, the
    facilitator's seat and own zones, and its setup - as one logged
    transaction, so the room's event log starts from an empty table.
    """
    if game_slug not in playable_slugs():
        raise UnknownExerciseError(f"There is no exercise called {game_slug!r}.")

    room = Room(
        code=generate_room_code(session), game_slug=game_slug, config=config or {}
    )
    session.add(room)
    session.flush()  # assigns room.id

    facilitator = Participant(
        room_id=room.id,
        cookie_id=facilitator_cookie_id,
        display_name=_dedupe_name(session, room.id, facilitator_name),
        connected=True,
    )
    session.add(facilitator)
    session.flush()  # assigns facilitator.id

    # Each room shuffles differently. The seed is kept on the table, so the
    # room's own shuffles can still be replayed exactly from its log.
    table = Table(rng=TableRng(seed=secrets.randbits(63)))
    seat_id, transaction = build_table(
        game_for(room), table, participant_id=facilitator.id
    )
    _apply_and_log(session, room, table, seat_id, transaction)
    facilitator.seat_id = seat_id
    room.facilitator_participant_id = facilitator.id

    save_table_state(session, room, table)
    return room, facilitator


def join_room(
    session: Session, *, code: str, cookie_id: str, display_name: str
) -> Participant:
    """Seat or reattach a browser at the room named by ``code``.

    A cookie that has already joined this room reclaims its existing
    participant row - and its seat, if it had one - rather than being seated
    twice. A closed room refuses new activity entirely.
    """
    room = get_room_by_code(session, code)
    if room is None:
        raise RoomNotFoundError(f"There is no room with the code {code!r}.")
    if room.status == "closed":
        raise RoomClosedError("This room is closed.")

    existing = get_participant(session, room.id, cookie_id)
    if existing is not None:
        existing.connected = True
        existing.last_seen_at = _now()
        if display_name.strip() and display_name.strip() != existing.display_name:
            existing.display_name = _dedupe_name(
                session, room.id, display_name, exclude_participant_id=existing.id
            )
        room.last_active_at = _now()
        return existing

    participant = Participant(
        room_id=room.id,
        cookie_id=cookie_id,
        display_name=_dedupe_name(session, room.id, display_name),
        connected=True,
        is_observer=True,
    )
    session.add(participant)
    session.flush()  # assigns participant.id

    table = load_table(session, room)
    seat = _find_free_seat(table)
    if seat is None and len(table.seats) < max_seats(room):
        seat_id, transaction = build_seat(
            game_for(room), table, participant_id=participant.id
        )
        _apply_and_log(session, room, table, seat_id, transaction)
        seat = table.seats[seat_id]
    if seat is not None:
        seat.participant_id = participant.id
        participant.seat_id = seat.id
        participant.is_observer = False
        save_table_state(session, room, table)

    room.last_active_at = _now()
    return participant


def claim_seat(
    session: Session, room: Room, participant: Participant, seat_id: str
) -> None:
    """Move ``participant`` into a specific, currently free seat."""
    table = load_table(session, room)
    seat = table.seats.get(seat_id)
    if seat is None:
        raise SeatUnavailableError(f"There is no seat {seat_id!r}.")
    if seat.participant_id not in (None, participant.id):
        raise SeatUnavailableError("That seat is already taken.")

    if participant.seat_id is not None and participant.seat_id in table.seats:
        table.seats[participant.seat_id].participant_id = None
    seat.participant_id = participant.id
    participant.seat_id = seat.id
    participant.is_observer = False
    save_table_state(session, room, table)


def release_seat(session: Session, room: Room, participant: Participant) -> None:
    """Free the seat ``participant`` holds, without changing observer status."""
    table = load_table(session, room)
    if participant.seat_id is not None and participant.seat_id in table.seats:
        table.seats[participant.seat_id].participant_id = None
        save_table_state(session, room, table)
    participant.seat_id = None


def make_observer(session: Session, room: Room, participant: Participant) -> None:
    """Free ``participant``'s seat and mark them an observer until they claim one."""
    release_seat(session, room, participant)
    participant.is_observer = True


def rename(
    session: Session, room: Room, participant: Participant, display_name: str
) -> None:
    """Change ``participant``'s display name, deduping against the room's others."""
    participant.display_name = _dedupe_name(
        session, room.id, display_name, exclude_participant_id=participant.id
    )


def remove_participant(session: Session, room: Room, participant: Participant) -> None:
    """Remove ``participant`` from the room entirely, freeing their seat."""
    table = load_table(session, room)
    if participant.seat_id is not None and participant.seat_id in table.seats:
        table.seats[participant.seat_id].participant_id = None
        save_table_state(session, room, table)
    session.delete(participant)


def close_room(session: Session, room: Room) -> None:
    """Close a room permanently. Closed rooms refuse joins and operations."""
    room.status = "closed"
    room.closed_at = _now()


def pause_room(session: Session, room: Room) -> None:
    """Mark a room paused - the facilitator-visible state, not a table freeze."""
    room.status = "paused"


def resume_room(session: Session, room: Room) -> None:
    """Return a paused room to normal activity."""
    room.status = "open"


# -- the one write path into a table's state -------------------------------


def next_seq(session: Session, room_id: str) -> int:
    stmt = select(func.max(Event.seq)).where(Event.room_id == room_id)
    last = session.execute(stmt).scalar_one_or_none()
    return (last or 0) + 1


def _op_payload(op: Operation) -> dict[str, object]:
    """``op``'s fields as a JSON-safe dict, for the event log.

    A transaction's steps are logged one by one with their own operation
    names, so a macro reads in the log as exactly what it did.
    """
    if isinstance(op, Transaction):
        return {
            "name": op.name,
            "label": op.label,
            "op_id": op.op_id,
            "steps": [
                {"op_type": type(step).__name__, "payload": _op_payload(step)}
                for step in op.steps
            ],
        }
    if not dataclasses.is_dataclass(op):
        raise TypeError(f"Operation {op!r} must be a dataclass to be logged.")
    # Round-tripping through json normalises tuples to lists and fails fast
    # if a game ever puts something non-JSON-safe in an operation's payload.
    raw = json.dumps(dataclasses.asdict(op))
    payload: dict[str, object] = json.loads(raw)
    return payload


def append_event(
    session: Session, room: Room, *, actor_seat: str | None, op: Operation
) -> int:
    """Append ``op`` to ``room``'s permanent log and return its sequence number.

    The log is append-only: this is the only function that writes to it, and
    nothing anywhere updates or deletes a row in it. The realtime layer owns
    a room's table in memory and calls this directly for the operations it
    has already applied; everything else goes through ``apply_op``, which
    applies and logs together.
    """
    seq = next_seq(session, room.id)
    session.add(
        Event(
            room_id=room.id,
            seq=seq,
            actor_seat=actor_seat,
            op_type=type(op).__name__,
            payload=_op_payload(op),
        )
    )
    # Flushed here so that a batch of events appended in one session sees its
    # own rows when it asks for the next sequence number.
    session.flush()
    room.last_active_at = _now()
    return seq


@dataclass(frozen=True)
class AppliedOp:
    """What happened when an operation was applied, for the caller's logging."""

    outcome: OpOutcome
    seq: int | None


def apply_op(session: Session, room: Room, actor_seat: str, op: Operation) -> AppliedOp:
    """Validate and apply ``op`` against ``room``'s table - the only write path.

    On success, the resulting patches are returned, the table's new state is
    persisted, and an event recording the operation is appended to the
    room's permanent log. On rejection, nothing is written. A retried
    ``op.op_id`` is a no-op per ``run_op`` - it reports Ok again, but nothing
    new is written here either, since nothing on the table actually changed.
    """
    if room.status == "closed":
        return AppliedOp(outcome=Reject("This room is closed."), seq=None)

    table = load_table(session, room)
    already_applied = op.op_id in table.applied_op_ids
    outcome = run_op(table, actor_seat, op)
    if not isinstance(outcome, Ok):
        return AppliedOp(outcome=outcome, seq=None)
    if already_applied:
        return AppliedOp(outcome=outcome, seq=None)

    seq = append_event(session, room, actor_seat=actor_seat, op=op)
    save_table_state(session, room, table)
    room.last_active_at = _now()
    return AppliedOp(outcome=outcome, seq=seq)


__all__ = [
    "AppliedOp",
    "CODE_ALPHABET",
    "CODE_LENGTH",
    "DEFAULT_MAX_SEATS",
    "RoomClosedError",
    "RoomError",
    "RoomNotFoundError",
    "SeatUnavailableError",
    "UnknownExerciseError",
    "append_event",
    "apply_op",
    "claim_seat",
    "close_room",
    "create_room",
    "game_for",
    "generate_room_code",
    "get_participant",
    "get_room",
    "get_room_by_code",
    "join_room",
    "load_table",
    "make_observer",
    "next_seq",
    "max_seats",
    "pause_room",
    "release_seat",
    "remove_participant",
    "rename",
    "resume_room",
    "save_live_table_state",
    "save_table_state",
]
