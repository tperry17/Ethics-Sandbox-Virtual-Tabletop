"""The realtime layer: transport and synchronisation, and nothing else.

One asyncio task owns each live room's table, so every operation against
that table is serialised by the queue feeding that task and no lock is
needed anywhere. Connections hand intents to the room task and read
whatever the room task decides to send back.

Two rules hold this module together.

Python is authoritative. A client proposes an intent; the room task decides
what actually happened by running the operation against the model, and the
client learns the result only as a projected patch. Nothing here knows a
rule of any exercise: it decodes an intent into a
:mod:`sandbox.model.ops` operation and lets the model judge it.

Nothing leaves this module unprojected. Every outbound table fact - a
snapshot or a patch - is built by ``project`` or ``project_patches`` for the
one viewer it is addressed to. There is deliberately no code path that
serialises a ``Table``, a ``Piece``, or a raw ``Patch`` straight to a
socket, and ``tests/test_live.py`` asserts as much adversarially.

Sequence numbers here are broadcast sequence numbers, assigned by the room
task and never by a client. They order what clients have been told, and let
a reconnecting client ask for "everything after 41". They are not the event
log's ``seq``, which counts durable operations in the database; a coalesced
drag produces many broadcasts and exactly one logged event.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from sandbox.db.engine import SessionLocal, session_scope
from sandbox.db.models import Participant, Room
from sandbox.model import (
    ClearInk,
    Deal,
    Despawn,
    Draw,
    EndShow,
    EraseInk,
    Flip,
    Grab,
    Group,
    InkAppend,
    InkBegin,
    InkEnd,
    Lock,
    Move,
    MoveToZone,
    Ok,
    Operation,
    OpOutcome,
    Patch,
    Peek,
    Point,
    Rect,
    Release,
    ReorderZ,
    ResetTable,
    ResetZone,
    Roll,
    Rotate,
    SetProp,
    ShowTo,
    Shuffle,
    Spawn,
    StackOnto,
    Table,
    Ungroup,
    Unlock,
    ViewTable,
    piece_actions,
    project,
    run_op,
)
from sandbox.model.entities import Geometry
from sandbox.model.visibility import project_patches
from sandbox.web import rooms
from sandbox.web.identity import participant_id_from_cookies

# -- timings ------------------------------------------------------------------
#
# CLAUDE.md's latency budget: the person dragging sees their own piece move
# immediately; everyone else may be 100 ms behind. Nothing here should be
# tuned below that.

TICK_SECONDS = 1 / 30
MOVE_FLUSH_SECONDS = 1 / 15
CURSOR_FLUSH_SECONDS = 1 / 10
CURSOR_STALE_SECONDS = 3.0
HOLD_TIMEOUT_SECONDS = 10.0

# A client that has not drained this many messages is more than two seconds
# behind at any plausible message rate, and is served a fresh snapshot
# instead of a backlog.
OUTBOUND_QUEUE_LIMIT = 120

# How many broadcasts a reconnecting client may have missed and still be
# caught up with patches rather than a whole new snapshot.
PATCH_HISTORY_LENGTH = 500

# CLAUDE.md / prompt 5: snapshot every 200 events and on every macro, so a
# late joiner never replays thousands of events.
SNAPSHOT_EVERY_EVENTS = 200

CLOSE_NOT_IN_ROOM = 4403


# -- the wire protocol, client to server ---------------------------------------


class HelloMessage(BaseModel):
    """First message on a socket. ``last_seq`` is 0 for a fresh connection."""

    type: Literal["hello"] = "hello"
    room_code: str
    last_seq: int = 0


class IntentMessage(BaseModel):
    """A proposed operation. The server decides whether it happened."""

    type: Literal["intent"] = "intent"
    client_id: str
    op_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class CursorMessage(BaseModel):
    """Where this viewer's pointer is. Ephemeral - never persisted."""

    type: Literal["cursor"] = "cursor"
    x: float
    y: float


class HeartbeatMessage(BaseModel):
    """Keeps an idle socket and its presence entry alive."""

    type: Literal["heartbeat"] = "heartbeat"


class MenuRequestMessage(BaseModel):
    """What may I do to this piece? The answer is a ``MenuMessage``."""

    type: Literal["menu_request"] = "menu_request"
    client_id: str
    piece_id: str


ClientMessage = Annotated[
    HelloMessage
    | IntentMessage
    | CursorMessage
    | HeartbeatMessage
    | MenuRequestMessage,
    Field(discriminator="type"),
]
CLIENT_MESSAGE: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


# -- the wire protocol, server to client ---------------------------------------


class PieceView(BaseModel):
    """One piece as this viewer is entitled to see it. Mirrors ``ViewPiece``."""

    id: str
    kind: str
    zone_id: str
    x: float
    y: float
    z: int
    rotation: float
    face_up: bool
    held_by: str | None
    locked: bool
    component_id: str | None
    revealed_to: list[str] = Field(default_factory=list)
    revealed_by: str | None = None


class RectView(BaseModel):
    """A rectangular zone outline in table coordinates."""

    shape: Literal["rect"] = "rect"
    x: float
    y: float
    width: float
    height: float


class PolygonView(BaseModel):
    """An arbitrary zone outline in table coordinates."""

    shape: Literal["polygon"] = "polygon"
    points: list[tuple[float, float]]


GeometryView = Annotated[RectView | PolygonView, Field(discriminator="shape")]


def _geometry_view(geometry: Geometry) -> RectView | PolygonView:
    if isinstance(geometry, Rect):
        return RectView(
            x=geometry.x, y=geometry.y, width=geometry.width, height=geometry.height
        )
    return PolygonView(points=[(x, y) for x, y in geometry.points])


class ZoneView(BaseModel):
    """A zone as this viewer may see it. Mirrors ``ViewZone``.

    The outline is not a secret: what is private about a private zone is the
    faces of the pieces in it, which ``project`` strips piece by piece.
    """

    id: str
    kind: str
    label: str
    geometry: GeometryView
    visibility: str
    layout: str
    owner_seat: str | None


class ComponentView(BaseModel):
    """What one component looks like, for a viewer entitled to see its face.

    A piece names its component; this is the only place the face of that
    component is described. A client is sent the catalog for the pieces it
    may see, and nothing about the ones it may not: a deck's faces are not
    in this list, because ``component_id`` is stripped from those pieces
    long before anything here is assembled.

    There is deliberately no per-component back. A client is never told
    which component a face-down piece is, so it could not look one up; a
    back that varied by component would announce, by varying, exactly what
    the projection went to the trouble of withholding.
    """

    id: str
    title: str | None = None
    body: str | None = None
    folio: str | None = None
    image: str | None = None
    tint_index: int | None = None
    width: float | None = None
    height: float | None = None


class MacroView(BaseModel):
    """One button in the table toolbar, as the exercise defines it.

    What the button does is entirely the server's business; the client knows
    only its id, its label, and whether to show it to this viewer.
    """

    id: str
    label: str
    hint: str | None = None
    facilitator_only: bool = False


class StrokeView(BaseModel):
    id: str
    seat_id: str
    colour: str
    width: float
    points: list[tuple[float, float]]


class SeatView(BaseModel):
    """A seat, with who is in it - the roster the header and table both use."""

    id: str
    label: str
    tint_index: int
    participant_id: str | None
    display_name: str | None
    is_facilitator: bool
    connected: bool


class TableView(BaseModel):
    """A projected table. Only ever built from ``project``."""

    pieces: list[PieceView]
    zones: list[ZoneView]
    seats: list[SeatView]
    strokes: list[StrokeView]
    version: int


class YouView(BaseModel):
    """Who the receiving browser is at this table."""

    participant_id: str
    seat_id: str | None
    display_name: str
    is_facilitator: bool
    is_observer: bool


class PatchView(BaseModel):
    """One projected change. Only ever built from ``project_patches``."""

    kind: str
    op: str
    entity_id: str | None
    fields: dict[str, Any]


class CursorView(BaseModel):
    seat_id: str
    x: float
    y: float


class SnapshotMessage(BaseModel):
    """A whole table, as one viewer may see it, plus what it takes to draw it.

    ``components`` and ``macros`` travel with the snapshot rather than being
    fetched separately so that a client is never briefly holding pieces it
    cannot draw or a toolbar it cannot label.
    """

    type: Literal["snapshot"] = "snapshot"
    seq: int
    view_table: TableView
    seats: list[SeatView]
    you: YouView
    components: list[ComponentView] = Field(default_factory=list)
    macros: list[MacroView] = Field(default_factory=list)


class PatchesMessage(BaseModel):
    """Projected changes, plus the faces of any components they newly name.

    A card that becomes visible to someone - drawn into their hand, shown to
    them - arrives with a ``component_id`` the snapshot never described.
    ``components`` carries what it looks like, for that recipient only.
    """

    type: Literal["patches"] = "patches"
    seq: int
    patches: list[PatchView]
    components: list[ComponentView] = Field(default_factory=list)


class AckMessage(BaseModel):
    """The intent ``client_id`` was accepted. What changed arrives as patches."""

    type: Literal["ack"] = "ack"
    client_id: str


class MenuItemView(BaseModel):
    """One context-menu entry: a label, and the intent that choosing it sends."""

    id: str
    label: str
    group: str | None
    op_type: str
    payload: dict[str, Any]


class MenuMessage(BaseModel):
    """What this viewer may do to one piece now, in the order to offer it."""

    type: Literal["menu"] = "menu"
    client_id: str
    piece_id: str
    items: list[MenuItemView]


class RejectMessage(BaseModel):
    """Why a proposed intent did not happen, in a sentence a person can read."""

    type: Literal["reject"] = "reject"
    client_id: str
    reason: str


class PresenceMessage(BaseModel):
    type: Literal["presence"] = "presence"
    seats: list[SeatView]
    cursors: list[CursorView]


class NoticeMessage(BaseModel):
    type: Literal["notice"] = "notice"
    level: Literal["info", "warning"] = "info"
    text: str


ServerMessage = (
    SnapshotMessage
    | PatchesMessage
    | AckMessage
    | MenuMessage
    | RejectMessage
    | PresenceMessage
    | NoticeMessage
)


# -- intents to operations ------------------------------------------------------

_OPERATION_TYPES: tuple[type, ...] = (
    Grab,
    Release,
    Move,
    MoveToZone,
    StackOnto,
    Flip,
    Rotate,
    ReorderZ,
    Shuffle,
    Draw,
    Deal,
    Roll,
    SetProp,
    Lock,
    Unlock,
    Group,
    Ungroup,
    Point,
    InkBegin,
    InkAppend,
    InkEnd,
    EraseInk,
    ClearInk,
    Spawn,
    Despawn,
    ResetZone,
    ResetTable,
    ShowTo,
    EndShow,
    Peek,
)


def _wire_name(operation_type: type) -> str:
    """``MoveToZone`` -> ``move_to_zone``: the name clients use on the wire."""
    name = operation_type.__name__
    out: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index > 0:
            out.append("_")
        out.append(char.lower())
    return "".join(out)


OPERATIONS: dict[str, type] = {_wire_name(cls): cls for cls in _OPERATION_TYPES}
_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    name: TypeAdapter(cls) for name, cls in OPERATIONS.items()
}

# Operations that rearrange the table wholesale. A snapshot is written after
# each of them so a late joiner starts from the new arrangement.
MACRO_OPERATIONS = frozenset(
    {
        "shuffle",
        "draw",
        "deal",
        "spawn",
        "despawn",
        "reset_zone",
        "reset_table",
    }
)


class IntentError(Exception):
    """The intent could not be read as an operation. Carries a readable reason."""


def encode_operation(operation: Operation) -> tuple[str, dict[str, Any]]:
    """The wire name and payload that ``decode_intent`` would read back as ``op``.

    ``op_id`` is left out: an operation offered on a menu has not happened
    yet, and the client that chooses it supplies a fresh one.
    """
    payload = TypeAdapter(type(operation)).dump_python(operation, mode="json")
    payload.pop("op_id", None)
    return _wire_name(type(operation)), payload


def decode_intent(op_type: str, payload: Mapping[str, Any]) -> Operation:
    """Turn a wire intent into a model operation, or say why it cannot be one.

    A client may supply its own ``op_id`` so that a retried intent is
    recognised as the same operation and applied once; if it does not, one
    is generated here.
    """
    adapter = _ADAPTERS.get(op_type)
    if adapter is None:
        raise IntentError(f"There is no operation called {op_type!r}.")
    try:
        operation: Operation = adapter.validate_python(dict(payload))
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "payload"
        raise IntentError(
            f"That {op_type} could not be read: {where} {first['msg'].lower()}."
        ) from error
    return operation


# -- connections ----------------------------------------------------------------


class MessageSink(Protocol):
    """Anything a room can write text frames to - in practice a WebSocket."""

    async def send_text(self, data: str) -> None: ...


@dataclass
class Connection:
    """One browser attached to one room, with its own outbound queue.

    The queue is what makes a slow reader everyone else's non-problem: it is
    bounded, and a connection that lets it fill has its backlog dropped and
    is resynchronised with a fresh snapshot rather than being allowed to
    hold up the room task.
    """

    id: str
    sink: MessageSink
    participant_id: str
    display_name: str
    seat_id: str | None
    is_facilitator: bool
    is_observer: bool
    queue: asyncio.Queue[str | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=OUTBOUND_QUEUE_LIMIT)
    )
    last_seq_sent: int = 0
    ready: bool = False
    # Every component whose face this connection has been sent, so a patch
    # carries a description only the first time it names one.
    known_components: set[str] = field(default_factory=set)

    def send(self, message: BaseModel) -> bool:
        """Queue ``message``. False means this connection has fallen behind."""
        try:
            self.queue.put_nowait(message.model_dump_json())
        except asyncio.QueueFull:
            self._drain()
            return False
        return True

    def _drain(self) -> None:
        while True:
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                return


# -- what the room task is asked to do -------------------------------------------


@dataclass(frozen=True)
class _Join:
    connection: Connection


@dataclass(frozen=True)
class _Leave:
    connection: Connection


@dataclass(frozen=True)
class _Inbound:
    connection: Connection
    message: ClientMessage


_Command = _Join | _Leave | _Inbound


@dataclass(frozen=True)
class _PendingEvent:
    """One operation waiting to be appended to the room's permanent log."""

    actor_seat: str | None
    operation: Operation


def _persist(
    factory: sessionmaker[Session],
    room_id: str,
    pending: Sequence[_PendingEvent],
    table: Table | None,
) -> None:
    """Append events and optionally snapshot, in a worker thread.

    Called only from the room task, so writes for one room stay ordered.
    """
    with session_scope(factory) as session:
        room = rooms.get_room(session, room_id)
        if room is None:
            return
        for entry in pending:
            rooms.append_event(
                session, room, actor_seat=entry.actor_seat, op=entry.operation
            )
        if table is not None:
            rooms.save_table_state(session, room, table)


def _load_room(
    factory: sessionmaker[Session], code: str
) -> tuple[Room, Table, dict[str, str]] | None:
    """The room row, its table, and seat-to-name map, read in a worker thread."""
    with session_scope(factory) as session:
        room = rooms.get_room_by_code(session, code)
        if room is None:
            return None
        table = rooms.load_table(session, room)
        names = {
            person.seat_id: person.display_name
            for person in room.participants
            if person.seat_id is not None
        }
        return room, table, names


def _load_participant(
    factory: sessionmaker[Session], code: str, cookie_id: str
) -> tuple[Room, Participant] | None:
    """Who this browser already is in this room, if it has joined it."""
    with session_scope(factory) as session:
        room = rooms.get_room_by_code(session, code)
        if room is None:
            return None
        participant = rooms.get_participant(session, room.id, cookie_id)
        if participant is None:
            return None
        participant.connected = True
        return room, participant


# -- the room task ----------------------------------------------------------------


class RoomRuntime:
    """One live room: its table, its connections, and the task that owns both.

    Every mutation of ``self.table`` happens inside ``_run``. Callers reach
    it only by putting a command on ``self._commands``, which is what makes
    "one asyncio task per room, no locks" true rather than aspirational.
    """

    def __init__(
        self, code: str, room_id: str, table: Table, names: dict[str, str], hub: LiveHub
    ) -> None:
        self.code = code
        self.room_id = room_id
        self.table = table
        self.seq = 0
        # What the pieces on this table look like, and what buttons the
        # toolbar offers. Both are the exercise's to fill: until game
        # definitions exist, a room has a table and no components or macros,
        # and the client draws generic backs and an empty toolbar.
        self.components: dict[str, ComponentView] = {}
        self.macros: tuple[MacroView, ...] = ()
        self._hub = hub
        self._names = names
        self._commands: asyncio.Queue[_Command] = asyncio.Queue()
        self._connections: dict[str, Connection] = {}
        self._history: deque[tuple[int, list[Patch]]] = deque(
            maxlen=PATCH_HISTORY_LENGTH
        )
        self._cursors: dict[str, tuple[float, float, float]] = {}
        self._pending_moves: dict[str, tuple[str, Move]] = {}
        self._unlogged_moves: dict[str, _PendingEvent] = {}
        self._holds: dict[str, tuple[str, float]] = {}
        self._pending_events: list[_PendingEvent] = []
        self._events_since_snapshot = 0
        self._snapshot_due = False
        self._presence_due = False
        self._last_move_flush = 0.0
        self._last_presence_flush = 0.0
        self._task: asyncio.Task[None] | None = None

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"room:{self.code}")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    # -- the outside world's only entry points --------------------------------

    async def join(self, connection: Connection) -> None:
        await self._commands.put(_Join(connection))

    async def leave(self, connection: Connection) -> None:
        await self._commands.put(_Leave(connection))

    async def submit(self, connection: Connection, message: ClientMessage) -> None:
        await self._commands.put(_Inbound(connection, message))

    async def drain(self) -> None:
        """Wait until every queued command has been handled. For tests."""
        await self._commands.join()

    # -- the loop --------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            try:
                command = await asyncio.wait_for(
                    self._commands.get(), timeout=TICK_SECONDS
                )
            except TimeoutError:
                command = None
            if command is not None:
                try:
                    await self._handle(command)
                finally:
                    self._commands.task_done()
            await self._tick()

    async def _tick(self) -> None:
        now = time.monotonic()
        if now - self._last_move_flush >= MOVE_FLUSH_SECONDS:
            self._last_move_flush = now
            self._flush_moves()
        self._expire_holds(now)
        if now - self._last_presence_flush >= CURSOR_FLUSH_SECONDS:
            self._last_presence_flush = now
            self._expire_cursors(now)
            if self._presence_due or self._cursors:
                self._presence_due = False
                self._broadcast_presence()
        await self._flush_persistence()

    # -- commands ---------------------------------------------------------------

    async def _handle(self, command: _Command) -> None:
        if isinstance(command, _Join):
            self._connections[command.connection.id] = command.connection
            if command.connection.seat_id is not None:
                self._names[command.connection.seat_id] = (
                    command.connection.display_name
                )
            self._presence_due = True
            return
        if isinstance(command, _Leave):
            self._on_leave(command.connection)
            return
        self._on_message(command.connection, command.message)

    def _on_leave(self, connection: Connection) -> None:
        self._connections.pop(connection.id, None)
        seat_id = connection.seat_id
        if seat_id is not None:
            self._cursors.pop(seat_id, None)
            self._release_seat_holds(seat_id)
        self._presence_due = True
        self._notice(f"{connection.display_name} has left the table.")

    def _on_message(self, connection: Connection, message: ClientMessage) -> None:
        if isinstance(message, HeartbeatMessage):
            return
        if isinstance(message, CursorMessage):
            if connection.seat_id is not None:
                self._cursors[connection.seat_id] = (
                    message.x,
                    message.y,
                    time.monotonic(),
                )
            return
        if isinstance(message, HelloMessage):
            self._on_hello(connection, message)
            return
        if isinstance(message, MenuRequestMessage):
            self._on_menu_request(connection, message)
            return
        self._on_intent(connection, message)

    def _on_hello(self, connection: Connection, message: HelloMessage) -> None:
        """Catch a connection up: patches since ``last_seq``, or a snapshot.

        Never a page reload. If the gap is bigger than the retained history,
        or this is a first connection, the answer is a whole new snapshot.
        """
        first_time = not connection.ready
        connection.ready = True
        missed = [
            (seq, patches) for seq, patches in self._history if seq > message.last_seq
        ]
        replayable = (
            not first_time
            and message.last_seq > 0
            and message.last_seq <= self.seq
            and (not missed or missed[0][0] == message.last_seq + 1)
        )
        if replayable:
            for seq, patches in missed:
                self._send_patches(connection, seq, patches)
            connection.last_seq_sent = self.seq
        else:
            self._send_snapshot(connection)
        self._presence_due = True
        if first_time:
            self._notice(
                f"{connection.display_name} has joined the table.",
                except_connection=connection,
            )

    def _on_intent(self, connection: Connection, message: IntentMessage) -> None:
        seat_id = connection.seat_id
        if seat_id is None:
            self._reject(
                connection, message.client_id, "Observers can watch but not act."
            )
            return
        try:
            operation = decode_intent(message.op_type, message.payload)
        except IntentError as error:
            self._reject(connection, message.client_id, str(error))
            return

        # Legality is judged now, against the current table, so the person
        # who tried gets an immediate, honest answer even for a move whose
        # broadcast is coalesced.
        reason = operation.validate(self.table, seat_id)
        if reason is not None:
            self._reject(connection, message.client_id, reason)
            return

        if isinstance(operation, Move):
            self._pending_moves[operation.piece_id] = (seat_id, operation)
            self._holds[operation.piece_id] = (seat_id, time.monotonic())
            connection.send(AckMessage(client_id=message.client_id))
            return

        if isinstance(operation, Grab):
            self._holds[operation.piece_id] = (seat_id, time.monotonic())
        if isinstance(operation, Release | MoveToZone | StackOnto):
            self._settle_piece(operation.piece_id)

        outcome = self._apply(seat_id, operation, log=True)
        if not isinstance(outcome, Ok):
            self._reject(connection, message.client_id, outcome.reason)
            return
        # Sent after the patches, so by the time the client hears "accepted"
        # it already holds the table that resulted.
        connection.send(AckMessage(client_id=message.client_id))

    def _on_menu_request(
        self, connection: Connection, message: MenuRequestMessage
    ) -> None:
        """Answer with what this viewer may do to one piece, judged by the model."""
        seat_id = connection.seat_id
        entries = (
            []
            if seat_id is None
            else piece_actions(self.table, message.piece_id, seat_id)
        )
        items = []
        for entry in entries:
            op_type, payload = encode_operation(entry.operation)
            label = entry.label
            name = None if entry.seat_id is None else self._names.get(entry.seat_id)
            if name is not None:
                label = name if entry.group == "Show to…" else f"{label} · {name}"
            items.append(
                MenuItemView(
                    id=entry.key,
                    label=label,
                    group=entry.group,
                    op_type=op_type,
                    payload=payload,
                )
            )
        connection.send(
            MenuMessage(
                client_id=message.client_id, piece_id=message.piece_id, items=items
            )
        )

    # -- applying and broadcasting ------------------------------------------------

    def _apply(self, seat_id: str, operation: Operation, *, log: bool) -> OpOutcome:
        """Run one operation against the table and broadcast what changed."""
        # A retried intent carries the op_id of one already applied. The
        # model absorbs it silently; the log must not gain a second copy.
        already_applied = operation.op_id in self.table.applied_op_ids
        outcome = run_op(self.table, seat_id, operation)
        if not isinstance(outcome, Ok):
            return outcome
        if log and not already_applied:
            self._pending_events.append(
                _PendingEvent(actor_seat=seat_id, operation=operation)
            )
            self._events_since_snapshot += 1
            if (
                _wire_name(type(operation)) in MACRO_OPERATIONS
                or self._events_since_snapshot >= SNAPSHOT_EVERY_EVENTS
            ):
                self._snapshot_due = True
                self._events_since_snapshot = 0
        if outcome.patches:
            self._broadcast_patches(outcome.patches)
        return outcome

    def _flush_moves(self) -> None:
        """Apply at most one move per piece per tick: the latest position wins.

        The intermediate positions of a drag are never applied and never
        logged. What lands in the event log is the position the piece was in
        when it was let go, written by ``_settle_piece``.
        """
        if not self._pending_moves:
            return
        pending = self._pending_moves
        self._pending_moves = {}
        for piece_id, (seat_id, operation) in pending.items():
            outcome = self._apply(seat_id, operation, log=False)
            if isinstance(outcome, Ok):
                self._unlogged_moves[piece_id] = _PendingEvent(
                    actor_seat=seat_id, operation=operation
                )

    def _settle_piece(self, piece_id: str) -> None:
        """Log the final position of a piece whose drag has just finished."""
        pending = self._pending_moves.pop(piece_id, None)
        if pending is not None:
            seat_id, operation = pending
            outcome = self._apply(seat_id, operation, log=False)
            if isinstance(outcome, Ok):
                self._unlogged_moves[piece_id] = _PendingEvent(
                    actor_seat=seat_id, operation=operation
                )
        settled = self._unlogged_moves.pop(piece_id, None)
        if settled is not None:
            self._pending_events.append(settled)
            self._events_since_snapshot += 1
        self._holds.pop(piece_id, None)

    def _expire_holds(self, now: float) -> None:
        """Release a soft lock nobody has touched for ten seconds."""
        stale = [
            (piece_id, seat_id)
            for piece_id, (seat_id, touched) in self._holds.items()
            if now - touched >= HOLD_TIMEOUT_SECONDS
        ]
        for piece_id, seat_id in stale:
            self._settle_piece(piece_id)
            self._apply(seat_id, Release(piece_id=piece_id), log=True)

    def _release_seat_holds(self, seat_id: str) -> None:
        """A disconnect drops every soft lock that seat was holding, at once."""
        held = [
            piece_id
            for piece_id, (holder, _touched) in self._holds.items()
            if holder == seat_id
        ]
        for piece_id in held:
            self._settle_piece(piece_id)
            self._apply(seat_id, Release(piece_id=piece_id), log=True)
        for piece in self.table.pieces.values():
            if piece.held_by == seat_id:
                self._apply(seat_id, Release(piece_id=piece.id), log=True)
        # A card is shown for as long as someone is there holding it up.
        for piece in list(self.table.pieces.values()):
            if piece.revealed_by == seat_id:
                self._apply(seat_id, EndShow(piece_id=piece.id), log=True)

    async def _flush_persistence(self) -> None:
        if not self._pending_events and not self._snapshot_due:
            return
        pending = self._pending_events
        self._pending_events = []
        table = self.table if self._snapshot_due else None
        self._snapshot_due = False
        await asyncio.to_thread(
            _persist, self._hub.session_factory, self.room_id, pending, table
        )

    # -- outbound -----------------------------------------------------------------

    def _seat_views(self) -> list[SeatView]:
        occupied = {
            connection.seat_id
            for connection in self._connections.values()
            if connection.seat_id is not None
        }
        return [
            SeatView(
                id=seat.id,
                label=seat.label,
                tint_index=seat.tint_index,
                participant_id=seat.participant_id,
                display_name=self._names.get(seat.id),
                is_facilitator=seat.is_facilitator,
                connected=seat.id in occupied,
            )
            for seat in sorted(self.table.seats.values(), key=lambda seat: seat.id)
        ]

    def _table_view(self, view: ViewTable, seats: list[SeatView]) -> TableView:
        return TableView(
            pieces=[
                PieceView(
                    id=piece.id,
                    kind=str(piece.kind),
                    zone_id=piece.zone_id,
                    x=piece.x,
                    y=piece.y,
                    z=piece.z,
                    rotation=piece.rotation,
                    face_up=piece.face_up,
                    held_by=piece.held_by,
                    locked=piece.locked,
                    component_id=piece.component_id,
                    revealed_to=list(piece.revealed_to),
                    revealed_by=piece.revealed_by,
                )
                for piece in view.pieces
            ],
            zones=[
                ZoneView(
                    id=zone.id,
                    kind=str(zone.kind),
                    label=zone.label,
                    geometry=_geometry_view(zone.geometry),
                    visibility=str(zone.visibility),
                    layout=str(zone.layout),
                    owner_seat=zone.owner_seat,
                )
                for zone in view.zones
            ],
            seats=seats,
            strokes=[
                StrokeView(
                    id=stroke.id,
                    seat_id=stroke.seat_id,
                    colour=stroke.colour,
                    width=stroke.width,
                    points=[(x, y) for x, y in stroke.points],
                )
                for stroke in view.strokes
            ],
            version=view.version,
        )

    def _components_for(self, view: ViewTable) -> list[ComponentView]:
        """The faces this viewer already holds, and not one more.

        ``project`` has already decided which pieces this viewer may see the
        face of; every other piece reached them with ``component_id`` set to
        None. Keying the catalog off what survived that projection is what
        keeps a deck's contents out of the catalog: send the whole catalog
        instead and the faces nobody has drawn yet arrive anyway.
        """
        wanted = {
            piece.component_id
            for piece in view.pieces
            if piece.component_id is not None
        }
        return [
            component
            for component_id, component in sorted(self.components.items())
            if component_id in wanted
        ]

    def _macros_for(self, connection: Connection) -> list[MacroView]:
        return [
            macro
            for macro in self.macros
            if connection.is_facilitator or not macro.facilitator_only
        ]

    def _send_snapshot(self, connection: Connection) -> None:
        seats = self._seat_views()
        view = project(self.table, connection.seat_id)
        components = self._components_for(view)
        connection.known_components = {component.id for component in components}
        message = SnapshotMessage(
            seq=self.seq,
            view_table=self._table_view(view, seats),
            seats=seats,
            you=YouView(
                participant_id=connection.participant_id,
                seat_id=connection.seat_id,
                display_name=connection.display_name,
                is_facilitator=connection.is_facilitator,
                is_observer=connection.is_observer,
            ),
            components=components,
            macros=self._macros_for(connection),
        )
        connection.last_seq_sent = self.seq
        connection.send(message)

    def _send_patches(
        self, connection: Connection, seq: int, patches: list[Patch]
    ) -> None:
        projected = project_patches(self.table, patches, connection.seat_id)
        if not projected:
            connection.last_seq_sent = seq
            return
        # Only components named by a patch that survived projection: a
        # piece this viewer may not see has already lost its component_id.
        named = {
            patch.fields["component_id"]
            for patch in projected
            if patch.kind == "piece"
            and isinstance(patch.fields.get("component_id"), str)
        }
        fresh = sorted(
            component_id
            for component_id in named
            if isinstance(component_id, str)
            and component_id not in connection.known_components
            and component_id in self.components
        )
        connection.known_components.update(fresh)
        message = PatchesMessage(
            seq=seq,
            components=[self.components[component_id] for component_id in fresh],
            patches=[
                PatchView(
                    kind=patch.kind,
                    op=patch.op,
                    entity_id=patch.entity_id,
                    fields=dict(patch.fields),
                )
                for patch in projected
            ],
        )
        if connection.send(message):
            connection.last_seq_sent = seq
        else:
            self._send_snapshot(connection)

    def _broadcast_patches(self, patches: list[Patch]) -> None:
        self.seq += 1
        self._history.append((self.seq, list(patches)))
        for connection in list(self._connections.values()):
            if connection.ready:
                self._send_patches(connection, self.seq, patches)

    def _broadcast_presence(self) -> None:
        seats = self._seat_views()
        cursors = [
            CursorView(seat_id=seat_id, x=x, y=y)
            for seat_id, (x, y, _at) in sorted(self._cursors.items())
        ]
        message = PresenceMessage(seats=seats, cursors=cursors)
        for connection in list(self._connections.values()):
            if connection.ready and not connection.send(message):
                self._send_snapshot(connection)

    def _expire_cursors(self, now: float) -> None:
        stale = [
            seat_id
            for seat_id, (_x, _y, at) in self._cursors.items()
            if now - at >= CURSOR_STALE_SECONDS
        ]
        for seat_id in stale:
            self._cursors.pop(seat_id, None)

    def _reject(self, connection: Connection, client_id: str, reason: str) -> None:
        connection.send(RejectMessage(client_id=client_id, reason=reason))

    def _notice(
        self,
        text: str,
        *,
        level: Literal["info", "warning"] = "info",
        except_connection: Connection | None = None,
    ) -> None:
        message = NoticeMessage(level=level, text=text)
        for connection in list(self._connections.values()):
            if connection is except_connection or not connection.ready:
                continue
            connection.send(message)


# -- the hub ------------------------------------------------------------------------


class LiveHub:
    """Every live room in this process, and the socket lifecycle around them."""

    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self.session_factory: sessionmaker[Session] = session_factory or SessionLocal
        self._rooms: dict[str, RoomRuntime] = {}
        self._lock = asyncio.Lock()

    async def runtime_for(self, code: str) -> RoomRuntime | None:
        """The task owning ``code``'s table, started on first use."""
        async with self._lock:
            existing = self._rooms.get(code)
            if existing is not None:
                return existing
            loaded = await asyncio.to_thread(_load_room, self.session_factory, code)
            if loaded is None:
                return None
            room, table, names = loaded
            runtime = RoomRuntime(room.code, room.id, table, names, self)
            runtime.start()
            self._rooms[room.code] = runtime
            return runtime

    async def close_room(self, code: str) -> None:
        async with self._lock:
            runtime = self._rooms.pop(code, None)
        if runtime is not None:
            await runtime.stop()

    async def shutdown(self) -> None:
        async with self._lock:
            runtimes = list(self._rooms.values())
            self._rooms.clear()
        for runtime in runtimes:
            await runtime.stop()

    async def attach(
        self,
        runtime: RoomRuntime,
        sink: MessageSink,
        *,
        participant_id: str,
        display_name: str,
        seat_id: str | None,
        is_facilitator: bool,
        is_observer: bool,
    ) -> tuple[Connection, asyncio.Task[None]]:
        """Register a connection and start the task that writes to its socket."""
        connection = Connection(
            id=uuid.uuid4().hex,
            sink=sink,
            participant_id=participant_id,
            display_name=display_name,
            seat_id=seat_id,
            is_facilitator=is_facilitator,
            is_observer=is_observer,
        )
        writer = asyncio.create_task(_write_forever(connection))
        await runtime.join(connection)
        return connection, writer

    async def detach(
        self, runtime: RoomRuntime, connection: Connection, writer: asyncio.Task[None]
    ) -> None:
        await runtime.leave(connection)
        writer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await writer
        if runtime.connection_count == 0:
            await self.close_room(runtime.code)

    async def serve(self, websocket: Any, code: str) -> None:
        """Run one browser's socket from accept to close.

        Identity is the same cookie the rest of the site uses: a socket from
        a browser that has not joined this room is refused rather than being
        allowed to join anonymously.
        """
        await websocket.accept()
        normalised = code.strip().upper()
        cookie_id = participant_id_from_cookies(websocket.cookies)
        found = (
            None
            if cookie_id is None
            else await asyncio.to_thread(
                _load_participant, self.session_factory, normalised, cookie_id
            )
        )
        if found is None:
            await websocket.send_text(
                NoticeMessage(
                    level="warning", text="Join this room before opening its table."
                ).model_dump_json()
            )
            await websocket.close(code=CLOSE_NOT_IN_ROOM)
            return
        room, participant = found
        runtime = await self.runtime_for(room.code)
        if runtime is None:
            await websocket.close(code=CLOSE_NOT_IN_ROOM)
            return

        connection, writer = await self.attach(
            runtime,
            websocket,
            participant_id=participant.id,
            display_name=participant.display_name,
            seat_id=participant.seat_id,
            is_facilitator=room.facilitator_participant_id == participant.id,
            is_observer=participant.is_observer,
        )
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = CLIENT_MESSAGE.validate_json(raw)
                except ValidationError:
                    connection.send(
                        NoticeMessage(
                            level="warning", text="That message was not understood."
                        )
                    )
                    continue
                await runtime.submit(connection, message)
        except Exception:  # noqa: BLE001 - any socket end means the same thing
            pass
        finally:
            await self.detach(runtime, connection, writer)


async def _write_forever(connection: Connection) -> None:
    """Drain one connection's queue onto its socket until cancelled."""
    while True:
        text = await connection.queue.get()
        if text is None:
            return
        await connection.sink.send_text(text)


hub = LiveHub()


__all__ = [
    "AckMessage",
    "CLIENT_MESSAGE",
    "HOLD_TIMEOUT_SECONDS",
    "MACRO_OPERATIONS",
    "OPERATIONS",
    "project",
    "OUTBOUND_QUEUE_LIMIT",
    "ClientMessage",
    "ComponentView",
    "Connection",
    "CursorMessage",
    "CursorView",
    "HeartbeatMessage",
    "HelloMessage",
    "IntentError",
    "IntentMessage",
    "GeometryView",
    "LiveHub",
    "MacroView",
    "MenuItemView",
    "MenuMessage",
    "MenuRequestMessage",
    "MessageSink",
    "NoticeMessage",
    "PatchView",
    "PatchesMessage",
    "PieceView",
    "PolygonView",
    "PresenceMessage",
    "RectView",
    "RejectMessage",
    "RoomRuntime",
    "SeatView",
    "ServerMessage",
    "SnapshotMessage",
    "StrokeView",
    "TableView",
    "YouView",
    "ZoneView",
    "decode_intent",
    "encode_operation",
    "hub",
]
