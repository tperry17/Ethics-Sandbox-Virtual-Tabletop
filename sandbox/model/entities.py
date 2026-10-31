"""The tabletop domain: pieces, zones, seats, ink, and the table that holds them.

Pure Python. No FastAPI, no SQLAlchemy, no asyncio, no I/O. Every function in
this package is deterministic given its inputs and, where noted, the table's
own seeded RNG.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sandbox.model.rng import TableRng
from sandbox.model.types import Layout, PieceKind, Visibility, ZoneKind


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle in table coordinates."""

    x: float
    y: float
    width: float
    height: float

    def contains_point(self, x: float, y: float) -> bool:
        within_x = self.x <= x <= self.x + self.width
        within_y = self.y <= y <= self.y + self.height
        return within_x and within_y


@dataclass(frozen=True)
class Polygon:
    """An arbitrary zone outline. Automatic placement treats it as one point."""

    points: tuple[tuple[float, float], ...]


Geometry = Rect | Polygon


# The room itself, acting for an activity's own button: a macro the definition
# gives its players may do what the exercise needs, such as turning over
# everyone's card, which no single player could do alone.
SYSTEM_SEAT = "room"


@dataclass
class Piece:
    """One physical object on the table.

    ``component_id`` names what the piece actually is (which card, which
    face-set of dice) and is the one field ``project`` may strip from a
    viewer who is not entitled to it. ``revealed_to`` and ``revealed_by``
    record a deliberate reveal in progress: who is being shown the face, and
    who is showing it. Neither is a secret - that a card is being shown, and
    to whom, is exactly what everyone else at the table should see.
    ``props`` carries whatever a game
    definition needs beyond the fields every piece has - a die's rolled
    value, a note's text.
    """

    id: str
    kind: PieceKind
    component_id: str
    zone_id: str
    x: float
    y: float
    z: int
    rotation: float = 0.0
    face_up: bool = True
    held_by: str | None = None
    locked: bool = False
    revealed_to: frozenset[str] = field(default_factory=frozenset)
    revealed_by: str | None = None
    group_id: str | None = None
    props: dict[str, object] = field(default_factory=dict)


def rolled_value(piece: Piece) -> str | None:
    """The face a die is showing, as text, or None for anything unrolled.

    A rolled die keeps its result in ``props["value"]``. Unlike the rest of
    ``props`` it is sent to browsers, but only to those entitled to the
    die's face, the same as its ``component_id``.
    """
    value = piece.props.get("value")
    return None if value is None else str(value)


@dataclass
class Zone:
    """A named area of the table with its own visibility and layout rule."""

    id: str
    kind: ZoneKind
    label: str
    geometry: Geometry
    visibility: Visibility
    layout: Layout
    owner_seat: str | None = None
    capacity: int | None = None
    owner_moves_only: bool = False
    """Whether only the owner (or the facilitator) may move pieces in or out.

    A zone can be public - everyone reads its faces - and still be one only
    its owner arranges: an open hand. Others reach it through an offer.
    """


@dataclass
class Seat:
    """One place at the table, whether or not anyone is sitting in it yet."""

    id: str
    label: str
    tint_index: int
    participant_id: str | None = None
    is_facilitator: bool = False


@dataclass
class Stroke:
    """One continuous pen mark, in a single seat's ink colour."""

    id: str
    seat_id: str
    colour: str
    width: float
    points: list[tuple[float, float]] = field(default_factory=list)
    created_at: float = 0.0
    closed: bool = False


@dataclass
class Offer:
    """One open proposal to swap pieces between two seats.

    ``give`` are the proposer's pieces, ``want`` the recipient's, the same
    number each way. It stays on the table, visible to everyone, until the
    recipient answers it or the proposer withdraws it.
    """

    id: str
    from_seat: str
    to_seat: str
    give: tuple[str, ...]
    want: tuple[str, ...]


@dataclass
class Activity:
    """A guided activity started in the room, for some of its seats.

    It begins as a sign-up (``status`` ``"signup"``) and runs once its zones
    have been laid out. ``zones`` names every zone it made, so ending it can
    take exactly those and their pieces away. ``kind`` names the game
    definition; the model does not know what that is.
    """

    id: str
    kind: str
    title: str
    min_players: int
    max_players: int
    seats: tuple[str, ...]
    status: str = "signup"
    zones: tuple[str, ...] = ()
    options: dict[str, str] = field(default_factory=dict)
    """The choices made when it was opened (which city, which phase)."""


@dataclass
class Table:
    """The whole state of one room's tabletop at one instant.

    Nothing outside ``sandbox.model.ops`` should mutate a Table's contents
    directly. Every change goes through an operation's ``apply``, called by
    ``run_op``, so that patches, idempotency, and the version counter stay
    correct together.
    """

    pieces: dict[str, Piece] = field(default_factory=dict)
    zones: dict[str, Zone] = field(default_factory=dict)
    seats: dict[str, Seat] = field(default_factory=dict)
    strokes: dict[str, Stroke] = field(default_factory=dict)
    offers: dict[str, Offer] = field(default_factory=dict)
    swapped: set[frozenset[str]] = field(default_factory=set)
    """Each pair of seats that has completed a swap with each other."""
    activities: dict[str, Activity] = field(default_factory=dict)
    activity_serial: int = 0
    rng: TableRng = field(default_factory=lambda: TableRng(seed=0))
    version: int = 0
    applied_op_ids: set[str] = field(default_factory=set)

    def pieces_in_zone(self, zone_id: str) -> list[Piece]:
        """Pieces currently in a zone, in ascending z-order (bottom to top)."""
        return sorted(
            (piece for piece in self.pieces.values() if piece.zone_id == zone_id),
            key=lambda piece: piece.z,
        )

    def top_z_in_zone(self, zone_id: str) -> int:
        pieces = self.pieces_in_zone(zone_id)
        return pieces[-1].z if pieces else 0

    def next_z_in_zone(self, zone_id: str) -> int:
        pieces = self.pieces_in_zone(zone_id)
        return pieces[-1].z + 1 if pieces else 0

    def is_facilitator(self, seat_id: str) -> bool:
        if seat_id == SYSTEM_SEAT:
            return True
        seat = self.seats.get(seat_id)
        return seat is not None and seat.is_facilitator
