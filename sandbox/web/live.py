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
import dataclasses
import secrets
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
from sandbox.games import GAMES, OPEN_ROOM_SLUG, Game
from sandbox.games.engine import (
    announcement,
    build_activity_start,
    build_macro,
    build_seat_move,
    may_use_facilitator_button,
)
from sandbox.games.pairing import may_pair, pair_outcome, pairing_choices
from sandbox.model import (
    SYSTEM_SEAT,
    AcceptSwap,
    AddSeat,
    AddZone,
    AssignClassTables,
    AssignSeat,
    ClassGroup,
    ClearClassTimer,
    ClearInk,
    Deal,
    DeclineSwap,
    Despawn,
    Draw,
    EndActivity,
    EndClass,
    EndShow,
    EraseInk,
    Flip,
    Grab,
    Group,
    InkAppend,
    InkBegin,
    InkEnd,
    JoinActivity,
    LeaveActivity,
    Lock,
    Move,
    MoveToZone,
    OfferSwap,
    Ok,
    OpenActivity,
    Operation,
    OpOutcome,
    PairTables,
    Patch,
    Peek,
    Point,
    PushClassPrompt,
    Rect,
    Reject,
    Release,
    ReleaseFacilitator,
    ReorderZ,
    ResetTable,
    ResetZone,
    Roll,
    Rotate,
    Seat,
    SetActivityPlayers,
    SetClassDecision,
    SetText,
    ShowTo,
    Shuffle,
    Spawn,
    StackOnto,
    StartClass,
    StartClassTimer,
    Table,
    TableRng,
    TakeFacilitator,
    Transaction,
    Ungroup,
    Unlock,
    UnpairTables,
    ViewTable,
    WithdrawSwap,
    Zone,
    piece_actions,
    project,
    run_op,
    sort_into_tables,
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
# How long a dropped participant keeps what they were holding or showing. A
# blip in the Wi-Fi must not drop a card in mid-drag; coming back inside this
# time keeps the hold.
LEAVE_GRACE_SECONDS = 10.0

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
    # Which run of the room ``last_seq`` belongs to (from the snapshot). A
    # client that was last connected to an earlier run of the server, or an
    # earlier life of this room, is sent a whole snapshot, never a replay.
    epoch: str | None = None


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
    value: str | None = None
    text: str | None = None


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
    owner_moves_only: bool = False


class OfferView(BaseModel):
    """An open swap offer. Mirrors ``ViewOffer``; the whole table sees it."""

    id: str
    from_seat: str
    to_seat: str
    give: list[str]
    want: list[str]


class ActivityView(BaseModel):
    """An activity in the room. Mirrors ``ViewActivity``."""

    id: str
    kind: str
    title: str
    min_players: int
    max_players: int
    seats: list[str]
    status: str
    options: dict[str, str] = Field(default_factory=dict)
    class_id: str = ""


class ClassPairView(BaseModel):
    """Two paired tables and, once both have decided, what follows."""

    first: str
    second: str
    first_decision: str | None = None
    second_decision: str | None = None
    first_proposed: str | None = None
    second_proposed: str | None = None
    outcome: str | None = None


class ClassPromptChoiceView(BaseModel):
    id: str
    text: str


class ClassView(BaseModel):
    """A class: one activity at several tables. Mirrors ``ViewClass``.

    The timer and the pushed prompt are for every screen. Pairing, decisions
    and outcomes are the facilitator's, so they are empty for anyone else.
    The panel never carries a card face or a token value.
    """

    id: str
    kind: str
    title: str
    tables: list[str]
    timer_remaining: float | None = None
    timer_seconds: int = 0
    prompt: str = ""
    prompt_serial: int = 0
    can_pair: bool = False
    pair_choices: list[str] = Field(default_factory=list)
    your_table: str = ""
    your_decision: str | None = None
    your_proposal: str | None = None
    pairs: list[ClassPairView] = Field(default_factory=list)
    prompt_choices: list[ClassPromptChoiceView] = Field(default_factory=list)


class ClassSortMessage(BaseModel):
    """A proposed sorting of people into tables. Sent to the facilitator only."""

    type: Literal["class_sort"] = "class_sort"
    class_id: str
    tables: list[list[str]]


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
    group: str | None = None
    badge: str | None = None
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
    confirm: str | None = None
    activity_id: str | None = None


class ActivityOptionChoiceView(BaseModel):
    id: str
    label: str


class ActivityOptionView(BaseModel):
    """A choice made when an activity is started, such as which city."""

    id: str
    label: str
    choices: list[ActivityOptionChoiceView]


class ActivityChoiceView(BaseModel):
    """An activity this room can start: what it is called and how many it takes."""

    slug: str
    title: str
    min_players: int
    max_players: int
    duration_minutes: int
    options: list[ActivityOptionView] = Field(default_factory=list)


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
    offers: list[OfferView] = Field(default_factory=list)
    swapped: list[tuple[str, str]] = Field(default_factory=list)
    activities: list[ActivityView] = Field(default_factory=list)


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
    epoch: str = ""
    view_table: TableView
    seats: list[SeatView]
    you: YouView
    components: list[ComponentView] = Field(default_factory=list)
    macros: list[MacroView] = Field(default_factory=list)
    activity_choices: list[ActivityChoiceView] = Field(default_factory=list)
    classes: list[ClassView] = Field(default_factory=list)


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
    | ClassSortMessage
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
    SetText,
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
    OfferSwap,
    AcceptSwap,
    DeclineSwap,
    WithdrawSwap,
    TakeFacilitator,
    ReleaseFacilitator,
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
        "transaction",
        "shuffle",
        "draw",
        "deal",
        "spawn",
        "despawn",
        "reset_zone",
        "reset_table",
    }
)


# The intent a toolbar button sends. It is not a model operation: the room
# asks the exercise's definition what pressing that button does now.
MACRO_INTENT = "macro"

# The intent that opens, joins, begins and ends an activity in the room.
ACTIVITY_INTENT = "activity"

# The intent that starts and runs a class: several tables of one activity.
CLASS_INTENT = "class"


def chosen_options(game: Game, sent: object) -> dict[str, str] | str:
    """The options a person chose for ``game``, or a sentence saying what is wrong.

    An option left out takes its first choice; one the definition does not
    offer, or a value it does not list, is refused.
    """
    given = sent if isinstance(sent, dict) else {}
    chosen = game.definition.default_options()
    for option_id, value in given.items():
        option = next((o for o in game.definition.options if o.id == option_id), None)
        if option is None or value not in {c.id for c in option.choices}:
            return "That choice is not one this activity offers."
        chosen[option_id] = value
    return chosen


def activity_choices() -> list[ActivityChoiceView]:
    """The activities any room can start: every game but the open room itself.

    Whether a game is in the public catalog (``listed``) is a separate matter.
    """
    return [
        ActivityChoiceView(
            slug=game.slug,
            title=game.title,
            min_players=game.definition.meta.players.min,
            max_players=game.definition.meta.players.max,
            duration_minutes=game.definition.meta.duration_minutes,
            options=[
                ActivityOptionView(
                    id=option.id,
                    label=option.label,
                    choices=[
                        ActivityOptionChoiceView(id=c.id, label=c.label)
                        for c in option.choices
                    ],
                )
                for option in game.definition.options
            ],
        )
        for game in GAMES.values()
        if game.slug != OPEN_ROOM_SLUG
    ]


def component_views(game: Game | None) -> dict[str, ComponentView]:
    """Every face the exercise defines, ready to send to whoever may see it."""
    if game is None:
        return {}
    return {
        component_id: ComponentView(
            id=component_id,
            title=face.title,
            body=face.body,
            folio=face.folio,
            image=face.image,
            group=face.group,
            badge=face.badge,
            tint_index=face.tint_index,
            width=face.width,
            height=face.height,
        )
        for component_id, face in game.faces().items()
    }


def macro_views(game: Game | None) -> tuple[MacroView, ...]:
    """The exercise's toolbar, in the order its definition lists the buttons."""
    if game is None:
        return ()
    return tuple(
        MacroView(
            id=macro.id,
            label=game.buttons[macro.id].label,
            hint=game.buttons[macro.id].hint,
            facilitator_only=macro.who == "facilitator",
            confirm=game.buttons[macro.id].confirm,
        )
        for macro in game.definition.macros
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
    # This person's seat and its own zones as the database has them. A seat
    # taken while the room was already live is not on the room task's table
    # yet; joining brings it there.
    stored_seat: tuple[Seat, tuple[Zone, ...]] | None = None

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


@dataclass(frozen=True)
class _SeatsChanged:
    """Who sits where changed in the database; here is every stored seat."""

    occupants: dict[str, str | None]
    names: dict[str, str]


@dataclass(frozen=True)
class _SeatTaken:
    """Someone sat down while the room was live; here is their stored seat."""

    stored: tuple[Seat, tuple[Zone, ...]]


_Command = _Join | _Leave | _Inbound | _SeatTaken | _SeatsChanged


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
            rooms.save_live_table_state(session, room, table)


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


def _stored_seat(
    session: Session, room: Room, seat_id: str | None
) -> tuple[Seat, tuple[Zone, ...]] | None:
    """A seat and the zones it owns, as the database has them."""
    if seat_id is None:
        return None
    table = rooms.load_table(session, room)
    seat = table.seats.get(seat_id)
    if seat is None:
        return None
    owned = tuple(zone for zone in table.zones.values() if zone.owner_seat == seat.id)
    return seat, owned


def _load_seat(
    factory: sessionmaker[Session], code: str, participant_id: str
) -> tuple[Seat, tuple[Zone, ...]] | None:
    """The stored seat of the participant ``participant_id`` in room ``code``."""
    with session_scope(factory) as session:
        room = rooms.get_room_by_code(session, code)
        if room is None:
            return None
        participant = next(
            (person for person in room.participants if person.id == participant_id),
            None,
        )
        if participant is None:
            return None
        return _stored_seat(session, room, participant.seat_id)


def _load_occupants(
    factory: sessionmaker[Session], code: str
) -> tuple[dict[str, str | None], dict[str, str]] | None:
    """Every stored seat's occupant, and the names of the people seated."""
    with session_scope(factory) as session:
        room = rooms.get_room_by_code(session, code)
        if room is None:
            return None
        table = rooms.load_table(session, room)
        occupants = {seat.id: seat.participant_id for seat in table.seats.values()}
        names = {
            person.seat_id: person.display_name
            for person in room.participants
            if person.seat_id is not None
        }
        return occupants, names


def _load_participant(
    factory: sessionmaker[Session], code: str, cookie_id: str
) -> tuple[Room, Participant, tuple[Seat, tuple[Zone, ...]] | None] | None:
    """Who this browser already is in this room, if it has joined it.

    Also their seat and its own zones as stored, for a room task that was
    already running when they sat down.
    """
    with session_scope(factory) as session:
        room = rooms.get_room_by_code(session, code)
        if room is None:
            return None
        participant = rooms.get_participant(session, room.id, cookie_id)
        if participant is None:
            return None
        participant.connected = True
        return room, participant, _stored_seat(session, room, participant.seat_id)


# -- the room task ----------------------------------------------------------------


class RoomRuntime:
    """One live room: its table, its connections, and the task that owns both.

    Every mutation of ``self.table`` happens inside ``_run``. Callers reach
    it only by putting a command on ``self._commands``, which is what makes
    "one asyncio task per room, no locks" true rather than aspirational.
    """

    def __init__(
        self,
        code: str,
        room_id: str,
        table: Table,
        names: dict[str, str],
        hub: LiveHub,
        game: Game | None = None,
    ) -> None:
        self.code = code
        self.room_id = room_id
        self.table = table
        self.seq = 0
        # Changes whenever this room is loaded, so a seq number from before a
        # restart is never mistaken for one from now.
        self.epoch = uuid.uuid4().hex
        # What the pieces on this table look like, and what buttons the
        # toolbar offers, both from the exercise's game definition. An
        # exercise without one has neither, and the client draws generic
        # backs and an empty toolbar.
        self.game = game
        # Every game's faces, since an activity started later deals its own.
        self.components: dict[str, ComponentView] = {}
        for each in (*GAMES.values(), *(() if game is None else (game,))):
            self.components.update(component_views(each))
        self.macros: tuple[MacroView, ...] = macro_views(game)
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
        # Pieces the facilitator took out of someone's hand mid-drag, and
        # whose hand it was. That person's drag is over: what they send for
        # the piece next is refused, until they pick it up afresh.
        self._taken: dict[str, str] = {}
        # Seats whose last connection closed, and when their holds are let go.
        self._leaving: dict[str, float] = {}
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
        """Stop the room task, then save the table exactly as it was left.

        A room's snapshot is otherwise written only every 200 events or after
        a macro, so without this last save a room everyone has left would
        come back as it stood at its last snapshot, losing every move since.
        """
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        for piece_id in list(self._pending_moves) + list(self._unlogged_moves):
            self._settle_piece(piece_id)
        self._snapshot_due = True
        await self._flush_persistence()

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

    async def seat_taken(self, stored: tuple[Seat, tuple[Zone, ...]]) -> None:
        await self._commands.put(_SeatTaken(stored))

    async def seats_changed(
        self, occupants: dict[str, str | None], names: dict[str, str]
    ) -> None:
        await self._commands.put(_SeatsChanged(occupants, names))

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
        self._expire_leavers(now)
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
                self._leaving.pop(command.connection.seat_id, None)
                self._names[command.connection.seat_id] = (
                    command.connection.display_name
                )
            if command.connection.stored_seat is not None:
                self._bring_seat(command.connection.stored_seat)
            self._presence_due = True
            return
        if isinstance(command, _SeatTaken):
            self._bring_seat(command.stored)
            self._presence_due = True
            return
        if isinstance(command, _SeatsChanged):
            self._seat_occupants(command.occupants, command.names)
            return
        if isinstance(command, _Leave):
            self._on_leave(command.connection)
            return
        self._on_message(command.connection, command.message)

    def _bring_seat(self, stored: tuple[Seat, tuple[Zone, ...]]) -> None:
        """Put a seat taken while this room was live onto this room's table.

        The room service added it, logged it and stored it; this table was
        loaded before that. Nothing is logged again. Everyone already here
        is sent the whole table afresh, because a seat and its zones are new
        outlines, and a patch only ever changes what a client already has.
        """
        if stored[0].id in self.table.seats:
            return
        seat, zones = stored
        steps: list[Operation] = [
            AddSeat(
                seat_id=seat.id,
                label=seat.label,
                tint_index=seat.tint_index,
                is_facilitator=seat.is_facilitator,
                participant_id=seat.participant_id,
            )
        ]
        steps.extend(
            AddZone(
                zone_id=zone.id,
                kind=zone.kind,
                label=zone.label,
                geometry=zone.geometry,
                visibility=zone.visibility,
                layout=zone.layout,
                owner_seat=zone.owner_seat,
                capacity=zone.capacity,
                owner_moves_only=zone.owner_moves_only,
            )
            for zone in zones
            if zone.id not in self.table.zones
        )
        outcome = run_op(
            self.table, seat.id, Transaction(steps=tuple(steps), name=f"seat:{seat.id}")
        )
        if not isinstance(outcome, Ok):
            return
        self._seat_latecomer(seat.id)
        self.seq += 1
        self._history.clear()
        self._snapshot_due = True
        for other in list(self._connections.values()):
            if other.ready:
                self._send_snapshot(other)

    def _seat_occupants(
        self, occupants: dict[str, str | None], names: dict[str, str]
    ) -> None:
        """Take who sits where from the database, which owns it."""
        for seat_id, participant_id in occupants.items():
            seat = self.table.seats.get(seat_id)
            if seat is None or seat.participant_id == participant_id:
                continue
            # Not logged: the room service logs seat changes, if anything does.
            outcome = run_op(
                self.table,
                seat_id,
                AssignSeat(seat_id=seat_id, participant_id=participant_id),
            )
            if isinstance(outcome, Ok) and outcome.patches:
                self._broadcast_patches(outcome.patches)
        self._names = dict(names)
        self._presence_due = True

    def _on_leave(self, connection: Connection) -> None:
        self._connections.pop(connection.id, None)
        seat_id = connection.seat_id
        if seat_id is not None:
            self._cursors.pop(seat_id, None)
            if not any(c.seat_id == seat_id for c in self._connections.values()):
                # Holds are let go after a grace period, in _tick, unless the
                # same seat comes back first.
                self._leaving[seat_id] = time.monotonic() + LEAVE_GRACE_SECONDS
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
        same_run = (
            message.epoch == self.epoch if message.epoch is not None else not first_time
        )
        replayable = (
            same_run
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
        if message.op_type == MACRO_INTENT:
            self._on_macro(connection, seat_id, message)
            return
        if message.op_type == ACTIVITY_INTENT:
            self._on_activity(connection, seat_id, message)
            return
        if message.op_type == CLASS_INTENT:
            self._on_class(connection, seat_id, message)
            return
        try:
            operation = decode_intent(message.op_type, message.payload)
        except IntentError as error:
            self._reject(connection, message.client_id, str(error))
            return

        piece_id = getattr(operation, "piece_id", None)
        if isinstance(piece_id, str) and self._taken.get(piece_id) == seat_id:
            if not isinstance(operation, Grab):
                self._reject(
                    connection, message.client_id, "The facilitator took that piece."
                )
                return
            del self._taken[piece_id]

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
        if isinstance(operation, TakeFacilitator | ReleaseFacilitator):
            # The toolbar differs for the facilitator, so everyone is sent
            # their table again.
            for other in list(self._connections.values()):
                if other.ready:
                    self._send_snapshot(other)

    def _on_activity(
        self, connection: Connection, seat_id: str, message: IntentMessage
    ) -> None:
        """Open, join, leave, begin, choose players for, or end an activity.

        Each is one model operation, or for beginning one transaction built
        from the activity's definition. When the last place is taken the
        activity begins by itself; the facilitator or a player may begin it
        sooner once the minimum have signed up.
        """
        payload = message.payload
        action = payload.get("action")
        activity_id = payload.get("activity_id")
        operation: Operation
        if action == "open":
            game = GAMES.get(str(payload.get("slug")))
            if game is None or game.slug == OPEN_ROOM_SLUG:
                self._reject(
                    connection, message.client_id, "There is no such activity."
                )
                return
            meta = game.definition.meta
            chosen = chosen_options(game, payload.get("options"))
            if isinstance(chosen, str):
                self._reject(connection, message.client_id, chosen)
                return
            operation = OpenActivity(
                kind=game.slug,
                title=game.title,
                min_players=meta.players.min,
                max_players=meta.players.max,
                options=tuple(chosen.items()),
            )
        elif action in ("join", "leave", "end", "begin", "choose") and isinstance(
            activity_id, str
        ):
            if action == "join":
                operation = JoinActivity(activity_id)
            elif action == "leave":
                operation = LeaveActivity(activity_id)
            elif action == "end":
                operation = EndActivity(activity_id)
            elif action == "choose":
                seats = payload.get("seats")
                if not isinstance(seats, list) or not all(
                    isinstance(item, str) for item in seats
                ):
                    self._reject(connection, message.client_id, "Choose some players.")
                    return
                operation = SetActivityPlayers(activity_id, tuple(seats))
            else:
                begun = self._begin(seat_id, activity_id)
                if isinstance(begun, Reject):
                    self._reject(connection, message.client_id, begun.reason)
                    return
                connection.send(AckMessage(client_id=message.client_id))
                self._resend_everyone()
                return
        else:
            self._reject(connection, message.client_id, "That was not understood.")
            return

        self._land_drags(list(self._pending_moves))
        reason = operation.validate(self.table, seat_id)
        if reason is not None:
            self._reject(connection, message.client_id, reason)
            return
        before = set(self.table.activities)
        outcome = self._apply(seat_id, operation, log=True)
        if not isinstance(outcome, Ok):
            self._reject(connection, message.client_id, outcome.reason)
            return
        connection.send(AckMessage(client_id=message.client_id))
        # A full sign-up begins at once.
        full = [
            a
            for a in self.table.activities.values()
            if a.status == "signup" and len(a.seats) >= a.max_players
        ]
        for activity in full:
            if activity.id in before or isinstance(operation, OpenActivity):
                self._begin(seat_id, activity.id)
        self._resend_everyone()

    def _seat_latecomer(self, seat_id: str) -> None:
        """Seat someone who arrives after a sort at the roomiest table.

        A table that has begun is given the new person's own zones.
        """
        seat = self.table.seats.get(seat_id)
        if seat is None or seat.is_facilitator or seat.participant_id is None:
            return
        for group in self.table.classes.values():
            tables = [self.table.activities[t] for t in group.tables]
            if not tables or not any(t.seats for t in tables):
                continue  # nobody has been sorted: people choose for themselves
            open_tables = [t for t in tables if len(t.seats) < t.max_players]
            if not open_tables:
                continue
            roomiest = min(open_tables, key=lambda t: len(t.seats) - t.max_players)
            game = GAMES.get(group.kind)
            if game is None:
                continue
            built = build_seat_move(game, self.table, SYSTEM_SEAT, seat_id, roomiest.id)
            if isinstance(built, Transaction):
                self._apply(SYSTEM_SEAT, built, log=True)
            return

    def _on_class(
        self, connection: Connection, seat_id: str, message: IntentMessage
    ) -> None:
        """Start, sort, begin, time, prompt, pair or end a class.

        Each is one model operation, logged like any other; beginning the
        tables is one transaction per table, built from the definition. The
        person who starts a class becomes the facilitator if nobody is.
        """
        payload = message.payload
        action = payload.get("action")
        class_id = payload.get("class_id")
        operation: Operation
        if action == "start":
            game = GAMES.get(str(payload.get("slug")))
            tables = payload.get("tables")
            if game is None or game.slug == OPEN_ROOM_SLUG:
                self._reject(
                    connection, message.client_id, "There is no such activity."
                )
                return
            if not isinstance(tables, int) or isinstance(tables, bool):
                self._reject(connection, message.client_id, "Choose how many tables.")
                return
            chosen = chosen_options(game, payload.get("options"))
            if isinstance(chosen, str):
                self._reject(connection, message.client_id, chosen)
                return
            if not any(s.is_facilitator for s in self.table.seats.values()):
                took = self._apply(seat_id, TakeFacilitator(), log=True)
                if not isinstance(took, Ok):
                    self._reject(connection, message.client_id, took.reason)
                    return
            meta = game.definition.meta
            operation = StartClass(
                kind=game.slug,
                title=game.title,
                min_players=meta.players.min,
                max_players=meta.players.max,
                tables=tables,
                options=tuple(chosen.items()),
            )
        elif isinstance(class_id, str) and action in {
            "sort_preview",
            "assign",
            "begin",
            "timer",
            "timer_clear",
            "prompt",
            "pair",
            "unpair",
            "decision",
            "move",
            "end",
        }:
            group = self.table.classes.get(class_id)
            if group is None:
                self._reject(
                    connection, message.client_id, "That class is not running any more."
                )
                return
            if action == "move":
                moved = self._move_person(seat_id, group, payload)
                if isinstance(moved, Reject):
                    self._reject(connection, message.client_id, moved.reason)
                    return
                connection.send(AckMessage(client_id=message.client_id))
                self._resend_everyone()
                return
            built = self._class_operation(seat_id, action, group, payload)
            if isinstance(built, str):
                self._reject(connection, message.client_id, built)
                return
            if built is None:
                # A preview, a begin: answered without one operation.
                if action == "sort_preview":
                    proposed = self._sort_proposal(group)
                    if isinstance(proposed, str):
                        self._reject(connection, message.client_id, proposed)
                        return
                    connection.send(
                        ClassSortMessage(
                            class_id=group.id, tables=[list(t) for t in proposed]
                        )
                    )
                    connection.send(AckMessage(client_id=message.client_id))
                    return
                begun = self._begin_class(seat_id, group.id)
                if isinstance(begun, Reject):
                    self._reject(connection, message.client_id, begun.reason)
                    return
                connection.send(AckMessage(client_id=message.client_id))
                self._resend_everyone()
                return
            operation = built
        else:
            self._reject(connection, message.client_id, "That was not understood.")
            return

        self._land_drags(list(self._pending_moves))
        reason = operation.validate(self.table, seat_id)
        if reason is not None:
            self._reject(connection, message.client_id, reason)
            return
        outcome = self._apply(seat_id, operation, log=True)
        if not isinstance(outcome, Ok):
            self._reject(connection, message.client_id, outcome.reason)
            return
        connection.send(AckMessage(client_id=message.client_id))
        self._resend_everyone()

    def _class_operation(
        self, seat_id: str, action: str, group: ClassGroup, payload: dict[str, Any]
    ) -> Operation | str | None:
        """The operation for an action on ``group``, a sentence, or None for none."""
        if action in ("sort_preview", "begin"):
            if not self.table.is_facilitator(seat_id):
                return "Only the facilitator can do that."
            return None
        game = GAMES.get(group.kind)
        if action == "assign":
            tables = payload.get("tables")
            if not isinstance(tables, list) or not all(
                isinstance(people, list) and all(isinstance(p, str) for p in people)
                for people in tables
            ):
                return "Give each table its people."
            return AssignClassTables(
                group.id, tuple(tuple(people) for people in tables)
            )
        if action == "timer":
            seconds = payload.get("seconds")
            if not isinstance(seconds, int) or isinstance(seconds, bool):
                return "Choose a time."
            return StartClassTimer(group.id, seconds, time.time())
        if action == "timer_clear":
            return ClearClassTimer(group.id)
        if action == "prompt":
            prompt_id = payload.get("prompt_id")
            if prompt_id in (None, ""):
                return PushClassPrompt(group.id, "")
            found = next(
                (p for p in (game.prompts if game else ()) if p.id == prompt_id), None
            )
            if found is None:
                return "That prompt is not one this activity has."
            return PushClassPrompt(group.id, found.text)
        if action in ("pair", "unpair", "decision"):
            if game is None or not may_pair(game, group.options):
                return "This activity does not pair tables."
            first, second = payload.get("first"), payload.get("second")
            if action == "pair":
                if not isinstance(first, str) or not isinstance(second, str):
                    return "Choose two tables."
                return PairTables(group.id, first, second)
            if action == "unpair":
                if not isinstance(first, str):
                    return "Choose a table."
                return UnpairTables(group.id, first)
            decision = payload.get("decision", "")
            if not isinstance(first, str) or not isinstance(decision, str):
                return "Choose a table and what it decided."
            if decision and decision not in pairing_choices(game, group.options):
                return "That is not a choice this activity offers."
            return SetClassDecision(group.id, first, decision)
        return EndClass(group.id)

    def _move_person(
        self, seat_id: str, group: ClassGroup, payload: dict[str, Any]
    ) -> OpOutcome:
        """Take someone off their table and seat them at another, begun or not."""
        if not self.table.is_facilitator(seat_id):
            return Reject("Only the facilitator can move people.")
        person, to = payload.get("seat_id"), payload.get("to")
        game = GAMES.get(group.kind)
        if game is None or not isinstance(person, str):
            return Reject("Choose a person to move.")
        if to is not None and (not isinstance(to, str) or to not in group.tables):
            return Reject("Choose a table of this class.")
        built = build_seat_move(game, self.table, seat_id, person, to)
        if not isinstance(built, Transaction):
            return built
        self._land_drags(list(self._pending_moves))
        outcome = self._apply(seat_id, built, log=True)
        if isinstance(outcome, Ok):
            self._notice("A person was moved to another table.")
        return outcome

    def _sort_proposal(self, group: ClassGroup) -> list[tuple[str, ...]] | str:
        """People dealt into the class's tables at random, to look at first.

        The draw uses a fresh generator, so previewing changes nothing and
        pressing "sort again" gives another; what is confirmed is the
        assignment itself, and that is what is logged.
        """
        people = sorted(
            seat.id
            for seat in self.table.seats.values()
            if seat.participant_id is not None and not seat.is_facilitator
        )
        limits = [
            (self.table.activities[t].min_players, self.table.activities[t].max_players)
            for t in group.tables
        ]
        return sort_into_tables(people, limits, TableRng(seed=secrets.randbits(32)))

    def _begin_class(self, seat_id: str, class_id: str) -> OpOutcome:
        """Begin every table that has the people it needs; say which could not."""
        group = self.table.classes.get(class_id)
        if group is None:
            return Reject("That class is not running any more.")
        if not self.table.is_facilitator(seat_id):
            return Reject("Only the facilitator can begin the tables.")
        began = 0
        waiting: list[str] = []
        for number, tid in enumerate(group.tables, start=1):
            activity = self.table.activities.get(tid)
            if activity is None or activity.status != "signup":
                continue
            if not activity.min_players <= len(activity.seats) <= activity.max_players:
                waiting.append(str(number))
                continue
            outcome = self._begin(seat_id, tid)
            if isinstance(outcome, Ok):
                began += 1
        if waiting:
            self._notice(
                f"Table {', '.join(waiting)} cannot begin yet: it needs a different "
                "number of people.",
                level="warning",
            )
        if began == 0 and waiting:
            return Reject("No table has the number of people it needs.")
        return Ok([])

    def _begin(self, seat_id: str, activity_id: str) -> OpOutcome:
        """Lay out an activity's zones and mark it running, as ``seat_id``."""
        activity = self.table.activities.get(activity_id)
        game = None if activity is None else GAMES.get(activity.kind)
        if activity is None or game is None:
            return Reject("That activity is not running any more.")
        if seat_id not in activity.seats and not self.table.is_facilitator(seat_id):
            return Reject("Only a player or the facilitator can begin it.")
        built = build_activity_start(game, self.table, seat_id, activity_id)
        if not isinstance(built, Transaction):
            return built
        return self._apply(seat_id, built, log=True)

    def _resend_everyone(self) -> None:
        """Each person's toolbar depends on the activities, so send them again."""
        for other in list(self._connections.values()):
            if other.ready:
                self._send_snapshot(other)

    def _on_macro(
        self, connection: Connection, seat_id: str, message: IntentMessage
    ) -> None:
        """A toolbar button: the definition says what it does, all at once.

        The whole macro is one transaction - every step applies or none
        does - logged as one event, snapshotted, and announced to the table.
        A repeat of the same intent is applied once, like any other.
        """
        macro_id = message.payload.get("macro_id")
        op_id = message.payload.get("op_id")
        activity_id = message.payload.get("activity_id")
        game = self.game
        if isinstance(activity_id, str):
            activity = self.table.activities.get(activity_id)
            game = None if activity is None else GAMES.get(activity.kind)
        else:
            activity_id = None
        if game is None or not isinstance(macro_id, str):
            self._reject(connection, message.client_id, "There is no such button.")
            return
        if isinstance(op_id, str) and op_id in self.table.applied_op_ids:
            connection.send(AckMessage(client_id=message.client_id))
            return
        built = build_macro(game, self.table, seat_id, macro_id, activity_id)
        if not isinstance(built, Transaction):
            self._reject(connection, message.client_id, built.reason)
            return
        if isinstance(op_id, str) and op_id:
            built = dataclasses.replace(built, op_id=op_id)
        # A drag still being coalesced lands before the macro, not after it.
        self._land_drags(list(self._pending_moves))
        outcome = self._apply(seat_id, built, log=True)
        if not isinstance(outcome, Ok):
            self._reject(connection, message.client_id, outcome.reason)
            return
        connection.send(AckMessage(client_id=message.client_id))
        text = announcement(game, macro_id, connection.display_name)
        if text:
            self._notice(text)

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
        # The facilitator may take a piece someone else is holding. Their
        # drag so far is landed and logged first, so the log reads in order.
        held_by_others = (
            {
                piece.id: piece.held_by
                for piece in self.table.pieces.values()
                if piece.held_by is not None and piece.held_by != seat_id
            }
            if self.table.is_facilitator(seat_id)
            else {}
        )
        if held_by_others:
            self._land_drags(list(held_by_others))
        outcome = run_op(self.table, seat_id, operation)
        if not isinstance(outcome, Ok):
            return outcome
        for piece_id, holder in held_by_others.items():
            piece = self.table.pieces.get(piece_id)
            if piece is None or piece.held_by != holder:
                self._taken[piece_id] = holder
                self._holds.pop(piece_id, None)
                self._pending_moves.pop(piece_id, None)
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

    def _land_drags(self, piece_ids: list[str]) -> None:
        """Apply and log where these drags have got to, leaving them held."""
        for piece_id in piece_ids:
            pending = self._pending_moves.pop(piece_id, None)
            if pending is not None:
                holder, move = pending
                if isinstance(self._apply(holder, move, log=False), Ok):
                    self._unlogged_moves[piece_id] = _PendingEvent(
                        actor_seat=holder, operation=move
                    )
            landed = self._unlogged_moves.pop(piece_id, None)
            if landed is not None:
                self._pending_events.append(landed)
                self._events_since_snapshot += 1

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

    def _expire_leavers(self, now: float) -> None:
        """Let go of what a seat held once its grace period has run out."""
        for seat_id, deadline in list(self._leaving.items()):
            if now < deadline:
                continue
            del self._leaving[seat_id]
            for piece_id, holder in list(self._taken.items()):
                if holder == seat_id:
                    del self._taken[piece_id]
            self._release_seat_holds(seat_id)

    def _release_seat_holds(self, seat_id: str) -> None:
        """Drop every soft lock a seat was holding, once its grace has run out."""
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
                    value=piece.value,
                    text=piece.text,
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
                    owner_moves_only=zone.owner_moves_only,
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
            offers=[
                OfferView(
                    id=offer.id,
                    from_seat=offer.from_seat,
                    to_seat=offer.to_seat,
                    give=list(offer.give),
                    want=list(offer.want),
                )
                for offer in view.offers
            ],
            swapped=list(view.swapped),
            activities=[
                ActivityView(
                    id=a.id,
                    kind=a.kind,
                    title=a.title,
                    min_players=a.min_players,
                    max_players=a.max_players,
                    seats=list(a.seats),
                    status=a.status,
                    options=dict(a.options),
                    class_id=a.class_id,
                )
                for a in view.activities
            ],
        )

    def _class_views(
        self, is_facilitator: bool, seat_id: str | None = None
    ) -> list[ClassView]:
        """Every class, as one viewer may see it.

        Decisions and outcomes are the facilitator's. Nothing here reads a
        piece, so no card face or token value can be in it.
        """
        now = time.time()
        views: list[ClassView] = []
        for group in self.table.classes.values():
            game = GAMES.get(group.kind)
            remaining = (
                None
                if group.timer_ends_at is None
                else max(0.0, group.timer_ends_at - now)
            )
            view = ClassView(
                id=group.id,
                kind=group.kind,
                title=group.title,
                tables=list(group.tables),
                timer_remaining=remaining,
                timer_seconds=group.timer_seconds,
                prompt=group.prompt,
                prompt_serial=group.prompt_serial,
            )
            if is_facilitator and game is not None:
                view.can_pair = may_pair(game, group.options)
                view.pair_choices = list(pairing_choices(game, group.options))
                view.prompt_choices = [
                    ClassPromptChoiceView(id=p.id, text=p.text) for p in game.prompts
                ]
                for first, second in group.pairs:
                    ours = group.decisions.get(first)
                    theirs = group.decisions.get(second)
                    view.pairs.append(
                        ClassPairView(
                            first=first,
                            second=second,
                            first_decision=ours,
                            second_decision=theirs,
                            first_proposed=group.proposed.get(first),
                            second_proposed=group.proposed.get(second),
                            outcome=(
                                pair_outcome(game, ours, theirs)
                                if ours is not None and theirs is not None
                                else None
                            ),
                        )
                    )
            elif game is not None and seat_id is not None:
                # Someone at a paired table proposes what their table chose;
                # the facilitator confirms it.
                mine = next(
                    (
                        t
                        for t in group.tables
                        if seat_id in self.table.activities[t].seats
                        and any(t in pair for pair in group.pairs)
                    ),
                    None,
                )
                if mine is not None:
                    view.your_table = mine
                    view.your_decision = group.decisions.get(mine)
                    view.your_proposal = group.proposed.get(mine)
                    view.pair_choices = list(pairing_choices(game, group.options))
            views.append(view)
        return views

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

    def _refresh_role(self, connection: Connection) -> None:
        """The table says who is the facilitator, and that changes as people play."""
        seat = connection.seat_id
        connection.is_facilitator = seat is not None and self.table.is_facilitator(seat)

    def _macros_for(self, connection: Connection) -> list[MacroView]:
        self._refresh_role(connection)
        views = [
            macro
            for macro in self.macros
            if connection.is_facilitator or not macro.facilitator_only
        ]
        seat = connection.seat_id
        for activity in self.table.activities.values():
            game = GAMES.get(activity.kind)
            mine = seat is not None and seat in activity.seats
            if game is None or activity.status != "running":
                continue
            if not (mine or connection.is_facilitator):
                continue
            allowed = seat is not None and may_use_facilitator_button(
                self.table, seat, activity.id
            )
            for macro in macro_views(game):
                if allowed or not macro.facilitator_only:
                    views.append(macro.model_copy(update={"activity_id": activity.id}))
        return views

    def _send_snapshot(self, connection: Connection) -> None:
        self._refresh_role(connection)
        seats = self._seat_views()
        view = project(self.table, connection.seat_id)
        components = self._components_for(view)
        connection.known_components = {component.id for component in components}
        message = SnapshotMessage(
            seq=self.seq,
            epoch=self.epoch,
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
            activity_choices=activity_choices(),
            classes=self._class_views(connection.is_facilitator, connection.seat_id),
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
            runtime = RoomRuntime(
                room.code, room.id, table, names, self, game=GAMES.get(room.game_slug)
            )
            runtime.start()
            self._rooms[room.code] = runtime
            return runtime

    async def seat_taken(self, code: str, participant_id: str) -> None:
        """Tell a live room that ``participant_id`` has just sat down in it.

        Called once the seat is committed. A room nobody has open does not
        need telling: it reads every seat from the database when it starts.
        Without this, a seat would reach a live room only when its owner's
        page connected, and a deal pressed in between would pass them by.
        """
        async with self._lock:
            runtime = self._rooms.get(code)
        if runtime is None:
            return
        stored = await asyncio.to_thread(
            _load_seat, self.session_factory, code, participant_id
        )
        if stored is not None:
            await runtime.seat_taken(stored)

    async def seats_changed(self, code: str) -> None:
        """Tell a live room that who sits where has changed in the database.

        Whoever calls ``rooms.claim_seat``, ``release_seat``,
        ``make_observer`` or ``remove_participant`` while a room may be live
        calls this once the change is committed. A room nobody has open
        reads its seats from the database when it starts.
        """
        async with self._lock:
            runtime = self._rooms.get(code)
        if runtime is None:
            return
        loaded = await asyncio.to_thread(_load_occupants, self.session_factory, code)
        if loaded is not None:
            await runtime.seats_changed(*loaded)

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
        stored_seat: tuple[Seat, tuple[Zone, ...]] | None = None,
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
            stored_seat=stored_seat,
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
        room, participant, stored_seat = found
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
            is_facilitator=False,  # read from the table once the room task has it
            is_observer=participant.is_observer,
            stored_seat=stored_seat,
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
    "MACRO_INTENT",
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
    "component_views",
    "decode_intent",
    "encode_operation",
    "hub",
    "macro_views",
]
