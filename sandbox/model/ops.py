"""Table operations: the only way a Table may change.

Each operation is a small, self-contained request: it carries its own
payload as fields, knows how to validate itself against the current table,
and knows how to apply itself. Never call ``apply`` directly - call
``run_op``, which enforces idempotency by operation id and advances the
table's version, so a retried message is harmless.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from sandbox.model.entities import (
    MAX_TEXT,
    MAX_TOKEN_TEXT,
    SYSTEM_SEAT,
    Geometry,
    Piece,
    Polygon,
    Rect,
    Seat,
    Stroke,
    Table,
    Zone,
    rolled_value,
    written_text,
)
from sandbox.model.layout import place_in_zone
from sandbox.model.results import Ok, OpOutcome, Patch, Reject
from sandbox.model.types import Layout, PieceKind, Visibility, ZoneKind
from sandbox.model.visibility import entitled_to_face


def new_op_id() -> str:
    """A fresh, globally unique operation id."""
    return uuid.uuid4().hex


class Operation(Protocol):
    """What every operation must provide. ``op_id`` is what makes a retry harmless."""

    @property
    def op_id(self) -> str: ...

    def validate(self, table: Table, actor_seat: str) -> str | None:
        """A reason a person could be shown that this move is illegal, or None."""
        ...

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        """Mutate ``table`` and return the patches describing what changed.

        Only ``run_op`` should call this, and only after ``validate`` has
        returned None.
        """
        ...


def run_op(table: Table, actor_seat: str, op: Operation) -> OpOutcome:
    """The one way to apply an operation to a table.

    A repeated ``op.op_id`` is a retried message, not a second request: the
    table already reflects it, so this returns ``Ok([])`` without calling
    ``apply`` again and without advancing the version a second time.
    """
    if op.op_id in table.applied_op_ids:
        return Ok([])
    reason = op.validate(table, actor_seat)
    if reason is not None:
        return Reject(reason)
    patches = op.apply(table, actor_seat)
    table.remember_op_id(op.op_id)
    table.version += 1
    return Ok(patches)


# -- shared helpers -----------------------------------------------------------


def _get_piece(table: Table, piece_id: str) -> Piece | None:
    return table.pieces.get(piece_id)


def _get_zone(table: Table, zone_id: str) -> Zone | None:
    return table.zones.get(zone_id)


def _reason_piece_missing(piece: Piece | None, piece_id: str) -> str | None:
    if piece is None:
        return f"There is no piece {piece_id!r} on the table."
    return None


def _reason_not_movable(table: Table, piece: Piece, actor_seat: str) -> str | None:
    """Shared legality check for grabbing, moving, flipping, and rotating.

    The facilitator may take a piece from anywhere: a locked one, one
    someone else is holding, one in someone else's hand. Anyone else may
    not touch a locked piece, a piece another seat is holding, or a piece
    resting in another seat's private zone - they may give a piece to
    someone's hand, but not take one out of it.
    """
    if table.is_facilitator(actor_seat):
        return None
    if piece.locked:
        return "That piece is locked."
    return _reason_out_of_reach(table, piece, actor_seat)


def _reason_out_of_reach(table: Table, piece: Piece, actor_seat: str) -> str | None:
    """Whether ``piece`` is out of ``actor_seat``'s reach, lock aside.

    Held by someone else, or resting in another seat's private zone: the
    same limits as moving it, without the lock, so that whoever could move a
    piece but for its lock may unlock it.
    """
    if table.is_facilitator(actor_seat):
        return None
    if piece.held_by is not None and piece.held_by != actor_seat:
        return "Someone else is already holding that piece."
    zone = table.zones.get(piece.zone_id)
    owned = (Visibility.PRIVATE_TO_OWNER, Visibility.FACILITATOR_ONLY)
    if (
        zone is not None
        and (zone.visibility in owned or zone.owner_moves_only)
        and zone.owner_seat is not None
        and zone.owner_seat != actor_seat
    ):
        return "That piece is in someone else's hand."
    return None


HAND_KINDS = frozenset({PieceKind.CARD, PieceKind.TILE, PieceKind.TOKEN})
"""What a hand holds: cards, tiles and tokens, nothing else."""


def _reason_not_for_hand(kind: PieceKind, zone: Zone) -> str | None:
    """Whether a piece of ``kind`` may go into ``zone``, if it is a hand."""
    if zone.kind is ZoneKind.HAND and kind not in HAND_KINDS:
        return "Only cards, tiles and tokens go in a hand."
    return None


def _reason_cannot_place_in(table: Table, zone: Zone, actor_seat: str) -> str | None:
    """Whether ``actor_seat`` may put a piece into ``zone``.

    Only an owner-moves-only zone refuses: its owner arranges it, and
    everyone else must make an offer instead.
    """
    if (
        zone.owner_moves_only
        and zone.owner_seat not in (None, actor_seat)
        and not table.is_facilitator(actor_seat)
    ):
        return f"Only its owner may put cards into {zone.label}. Make an offer."
    return None


def _reason_cannot_take_from(table: Table, zone: Zone, actor_seat: str) -> str | None:
    """Whether ``actor_seat`` may take pieces out of ``zone`` as a whole."""
    if table.is_facilitator(actor_seat):
        return None
    owned = (Visibility.PRIVATE_TO_OWNER, Visibility.FACILITATOR_ONLY)
    restricted = zone.visibility in owned or zone.owner_moves_only
    if restricted and zone.owner_seat not in (None, actor_seat):
        return f"Only its owner or the facilitator may take from {zone.label}."
    if any(
        piece.held_by not in (None, actor_seat)
        for piece in table.pieces_in_zone(zone.id)
    ):
        return f"Someone is holding a piece from {zone.label}."
    return None


def _take_from_holder(piece: Piece, actor_seat: str) -> None:
    """A piece someone else was holding is no longer theirs once it is taken."""
    if piece.held_by is not None and piece.held_by != actor_seat:
        piece.held_by = None


def _piece_patch(piece: Piece) -> Patch:
    return Patch(
        kind="piece",
        op="upsert",
        entity_id=piece.id,
        fields={
            # ``kind`` is repeated on every piece patch, not only the first,
            # because a client that learns of a piece through a patch - one
            # spawned after it connected - has nothing else to tell it what
            # shape to draw.
            "kind": str(piece.kind),
            "zone_id": piece.zone_id,
            "x": piece.x,
            "y": piece.y,
            "z": piece.z,
            "rotation": piece.rotation,
            "face_up": piece.face_up,
            "held_by": piece.held_by,
            "locked": piece.locked,
            "component_id": piece.component_id,
            "group_id": piece.group_id,
            "revealed_to": sorted(piece.revealed_to),
            "revealed_by": piece.revealed_by,
            "value": rolled_value(piece),
            "text": written_text(piece),
        },
    )


def _turn_up_on_arrival(piece: Piece, source: Zone | None, destination: Zone) -> None:
    """A card drawn off a deck, or put into a hand or a discard pile, lands face up.

    Drawn off a deck (into anything but another deck) it is turned over, as
    a card picked off a pile is; put into a private hand it is turned so its
    owner can read it, as a dealt card is; a discard pile is always face up.
    Who may see the face is still the zone's visibility: a card face up in
    someone's hand shows only to them. A card going into a deck, or into a
    zone that hides every face, is left as it is.
    """
    if piece.kind is not PieceKind.CARD:
        return
    if destination.kind is ZoneKind.DECK or destination.visibility is Visibility.HIDDEN:
        return
    drawn = source is not None and source.kind is ZoneKind.DECK
    into_hand = destination.visibility is Visibility.PRIVATE_TO_OWNER
    if drawn or into_hand or _always_face_up(destination):
        piece.face_up = True


def _always_face_up(zone: Zone) -> bool:
    """A discard pile shows every card in it face up, however it got there."""
    return zone.kind is ZoneKind.DISCARD and zone.visibility is not Visibility.HIDDEN


def _clear_reveal(piece: Piece) -> None:
    """End any reveal in progress: a piece that moves is no longer being shown."""
    piece.revealed_to = frozenset()
    piece.revealed_by = None


def _stroke_patch(stroke: Stroke) -> Patch:
    return Patch(
        kind="stroke",
        op="upsert",
        entity_id=stroke.id,
        fields={
            "seat_id": stroke.seat_id,
            "colour": stroke.colour,
            "width": stroke.width,
            "points": list(stroke.points),
            "closed": stroke.closed,
        },
    )


# -- grabbing, moving, and orienting ------------------------------------------


@dataclass(frozen=True)
class Grab:
    """Pick a piece up. While held, no one else may move it."""

    piece_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        return _reason_not_movable(table, piece, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        piece.held_by = actor_seat
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class Release:
    """Put a held piece back down."""

    piece_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        if (
            piece.held_by is not None
            and piece.held_by != actor_seat
            and not table.is_facilitator(actor_seat)
        ):
            return "You are not holding that piece."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        piece.held_by = None
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class Move:
    """Move a piece within its current zone."""

    piece_id: str
    x: float
    y: float
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        return _reason_not_movable(table, piece, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        _take_from_holder(piece, actor_seat)
        piece.x, piece.y = self.x, self.y
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class MoveToZone:
    """Move a piece into a different zone, atomically re-placing it there.

    In a free-layout zone, ``x``/``y`` say where the piece lands. Anywhere
    else - and whenever they are omitted - the destination zone's layout
    decides: a card let go over a deck joins the deck, wherever on its
    outline the hand happened to open. Because this is one operation, a
    piece moving into a private zone never passes through an intermediate
    state where its true face is visible to someone not entitled to it.
    """

    piece_id: str
    zone_id: str
    x: float | None = None
    y: float | None = None
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        if (reason := _reason_not_movable(table, piece, actor_seat)) is not None:
            return reason
        zone = _get_zone(table, self.zone_id)
        if zone is None:
            return f"There is no zone {self.zone_id!r} on the table."
        if (reason := _reason_cannot_place_in(table, zone, actor_seat)) is not None:
            return reason
        if (reason := _reason_not_for_hand(piece.kind, zone)) is not None:
            return reason
        already_there = piece.zone_id == zone.id
        if (
            zone.capacity is not None
            and not already_there
            and len(table.pieces_in_zone(zone.id)) >= zone.capacity
        ):
            return f"{zone.label} is full."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        zone = table.zones[self.zone_id]
        _take_from_holder(piece, actor_seat)
        if piece.zone_id != zone.id:
            _turn_up_on_arrival(piece, table.zones.get(piece.zone_id), zone)
        piece.zone_id = zone.id
        piece.z = table.next_z_in_zone(zone.id)
        _clear_reveal(piece)
        if self.x is not None and self.y is not None and zone.layout is Layout.FREE:
            piece.x, piece.y = self.x, self.y
        else:
            index = len(table.pieces_in_zone(zone.id)) - 1
            x, y, rotation = place_in_zone(zone, index=index, count=index + 1)
            piece.x, piece.y, piece.rotation = x, y, rotation
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class StackOnto:
    """Put one piece on top of another, wherever that one is.

    The piece joins the other's zone, takes its position and rotation, and
    goes on top of everything else in that zone. A stack is nothing more
    than pieces sharing a spot; taking the top one off is an ordinary move.
    """

    piece_id: str
    onto_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        onto = _get_piece(table, self.onto_id)
        if (reason := _reason_piece_missing(onto, self.onto_id)) is not None:
            return reason
        assert piece is not None and onto is not None
        if piece.id == onto.id:
            return "A piece cannot be stacked on itself."
        if (reason := _reason_not_movable(table, piece, actor_seat)) is not None:
            return reason
        zone = table.zones.get(onto.zone_id)
        if zone is None:
            return f"There is no zone {onto.zone_id!r} on the table."
        if (reason := _reason_cannot_place_in(table, zone, actor_seat)) is not None:
            return reason
        if (reason := _reason_not_for_hand(piece.kind, zone)) is not None:
            return reason
        if (
            zone.capacity is not None
            and piece.zone_id != zone.id
            and len(table.pieces_in_zone(zone.id)) >= zone.capacity
        ):
            return f"{zone.label} is full."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        onto = table.pieces[self.onto_id]
        _take_from_holder(piece, actor_seat)
        if piece.zone_id != onto.zone_id:
            _clear_reveal(piece)
            _turn_up_on_arrival(
                piece, table.zones.get(piece.zone_id), table.zones[onto.zone_id]
            )
        piece.zone_id = onto.zone_id
        piece.z = (
            max(p.z for p in table.pieces_in_zone(onto.zone_id) if p.id != piece.id) + 1
        )
        piece.x, piece.y, piece.rotation = onto.x, onto.y, onto.rotation
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class Flip:
    """Turn a piece over, or set it to a specific face."""

    piece_id: str
    face_up: bool | None = None
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        if (reason := _reason_not_movable(table, piece, actor_seat)) is not None:
            return reason
        # A card is turned face up only once it is off the deck. Turning one
        # face down in a deck is still allowed: cards go back into a deck
        # face down.
        face_up = self.face_up if self.face_up is not None else not piece.face_up
        zone = table.zones.get(piece.zone_id)
        if (
            face_up
            and not piece.face_up
            and piece.kind is PieceKind.CARD
            and zone is not None
            and zone.kind is ZoneKind.DECK
        ):
            return (
                "A card in a deck cannot be turned face up. Take it off the deck first."
            )
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        piece.face_up = self.face_up if self.face_up is not None else not piece.face_up
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class Rotate:
    """Turn a piece by a number of degrees, positive being clockwise."""

    piece_id: str
    degrees: float = 90.0
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        return _reason_not_movable(table, piece, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        piece.rotation = (piece.rotation + self.degrees) % 360
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class ReorderZ:
    """Send a piece to the top or bottom of its zone's stacking order."""

    piece_id: str
    to_top: bool = True
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        return _reason_not_movable(table, piece, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        siblings = [p for p in table.pieces_in_zone(piece.zone_id) if p.id != piece.id]
        patches = [_piece_patch(piece)]
        if self.to_top:
            piece.z = (siblings[-1].z + 1) if siblings else 0
        else:
            piece.z = (siblings[0].z - 1) if siblings else 0
            for sibling in siblings:
                sibling.z += 1
                patches.append(_piece_patch(sibling))
        return patches


# -- decks, dealing, and dice --------------------------------------------------


@dataclass(frozen=True)
class Shuffle:
    """Shuffle the pieces within a zone, using the table's RNG.

    What moves is what each piece *is* - its component, kind, face and
    props - not the piece itself. Every piece keeps its id, its place and its
    z, and comes out of the shuffle as a random one of the cards that went
    in. Reordering z instead would leave each piece's id attached to the same
    card, and anyone who had seen a card face up, then watched it go into the
    deck, could follow its id through the shuffle and into someone's hand.
    """

    zone_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        zone = _get_zone(table, self.zone_id)
        if zone is None:
            return f"There is no zone {self.zone_id!r} on the table."
        # Even the facilitator does not shuffle a card out from under the
        # hand holding it: what that hand holds would change mid-drag.
        if any(piece.held_by is not None for piece in table.pieces_in_zone(zone.id)):
            return f"Someone is holding a piece from {zone.label}."
        return _reason_cannot_take_from(table, zone, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        pieces = table.pieces_in_zone(self.zone_id)
        if len(pieces) <= 1:
            return []
        identities = [
            (piece.kind, piece.component_id, piece.face_up, dict(piece.props))
            for piece in pieces
        ]
        order = table.rng.shuffled_indices(len(pieces))
        for piece, source in zip(pieces, order, strict=True):
            kind, component_id, face_up, props = identities[source]
            piece.kind, piece.component_id = kind, component_id
            piece.face_up, piece.props = face_up, props
            # A reveal names a piece, and the piece is now a different card.
            _clear_reveal(piece)
        # Shuffling face-down cards changes nothing anyone can see, so the
        # shuffle itself is told, for the table to show. Who shuffled which
        # pile is public; the order is not in it.
        shuffled = Patch(
            kind="table",
            op="event",
            entity_id=None,
            fields={"type": "shuffle", "zone_id": self.zone_id, "by_seat": actor_seat},
        )
        return [*(_piece_patch(piece) for piece in pieces), shuffled]


@dataclass(frozen=True)
class Draw:
    """Move the top ``count`` pieces of one zone into another."""

    count: int
    from_zone: str
    to_zone: str
    face_up: bool | None = None
    """Turn each drawn piece this way up; None leaves it as it came off the pile."""
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if self.count < 1:
            return "Cannot draw fewer than one piece."
        source = _get_zone(table, self.from_zone)
        if source is None:
            return f"There is no zone {self.from_zone!r} on the table."
        destination = _get_zone(table, self.to_zone)
        if destination is None:
            return f"There is no zone {self.to_zone!r} on the table."
        available = table.pieces_in_zone(self.from_zone)
        if len(available) < self.count:
            return f"Only {len(available)} pieces remain in {source.label}."
        for piece in available[-self.count :]:
            if (reason := _reason_not_for_hand(piece.kind, destination)) is not None:
                return reason
        return _reason_cannot_take_from(table, source, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        destination = table.zones[self.to_zone]
        drawn = table.pieces_in_zone(self.from_zone)[-self.count :]
        patches = []
        for piece in drawn:
            _take_from_holder(piece, actor_seat)
            next_z = table.next_z_in_zone(destination.id)
            index = len(table.pieces_in_zone(destination.id))
            piece.zone_id = destination.id
            piece.z = next_z
            x, y, rotation = place_in_zone(destination, index=index, count=index + 1)
            piece.x, piece.y, piece.rotation = x, y, rotation
            if self.face_up is not None:
                piece.face_up = self.face_up
            elif piece.kind is PieceKind.CARD and _always_face_up(destination):
                piece.face_up = True
            _clear_reveal(piece)
            patches.append(_piece_patch(piece))
        return patches


@dataclass(frozen=True)
class Deal:
    """Deal from one zone to several, one piece at a time, round by round.

    Matches how a person deals a real deck: each destination gets one piece
    per round rather than one destination getting all of theirs before the
    next.
    """

    from_zone: str
    to_zones: tuple[str, ...]
    count_each: int
    face_up: bool | None = None
    """Turn each dealt piece this way up; None leaves it as it came off the pile."""
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if self.count_each < 1:
            return "Cannot deal fewer than one piece each."
        if not self.to_zones:
            return "Deal needs at least one destination zone."
        source = _get_zone(table, self.from_zone)
        if source is None:
            return f"There is no zone {self.from_zone!r} on the table."
        for zone_id in self.to_zones:
            if _get_zone(table, zone_id) is None:
                return f"There is no zone {zone_id!r} on the table."
        needed = self.count_each * len(self.to_zones)
        pile = table.pieces_in_zone(self.from_zone)
        available = len(pile)
        if available < needed:
            return (
                f"Only {available} pieces remain in {source.label}, "
                f"but dealing needs {needed}."
            )
        # Dealt from the top, round by round: the n-th piece off the top goes
        # to destination n modulo their number.
        dealt = list(reversed(pile))[:needed]
        for index, piece in enumerate(dealt):
            zone = table.zones[self.to_zones[index % len(self.to_zones)]]
            if (reason := _reason_not_for_hand(piece.kind, zone)) is not None:
                return reason
        return _reason_cannot_take_from(table, source, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        patches: list[Patch] = []
        for _round in range(self.count_each):
            for zone_id in self.to_zones:
                draw = Draw(
                    count=1,
                    from_zone=self.from_zone,
                    to_zone=zone_id,
                    face_up=self.face_up,
                    op_id=new_op_id(),
                )
                patches.extend(draw.apply(table, actor_seat))
        return patches


@dataclass(frozen=True)
class Roll:
    """Roll a die, or every die in a zone, drawing faces from the table's RNG.

    A die piece carries its faces as ``props["faces"]``, a non-empty list.
    """

    target_id: str
    op_id: str = field(default_factory=new_op_id)

    def _dice(self, table: Table) -> list[Piece] | None:
        piece = _get_piece(table, self.target_id)
        if piece is not None:
            return [piece]
        if self.target_id in table.zones:
            zone_pieces = table.pieces_in_zone(self.target_id)
            return [p for p in zone_pieces if p.kind is PieceKind.DIE]
        return None

    def validate(self, table: Table, actor_seat: str) -> str | None:
        dice = self._dice(table)
        if dice is None:
            return f"There is no piece or zone {self.target_id!r} on the table."
        for die in dice:
            if die.kind is not PieceKind.DIE:
                return f"{die.id} is not a die."
            faces = die.props.get("faces")
            if not isinstance(faces, list) or not faces:
                return f"{die.id} has no faces to roll."
            if die.held_by is not None and die.held_by != actor_seat:
                return "Someone else is holding that die."
            if die.locked and not table.is_facilitator(actor_seat):
                return "That die is locked."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        dice = self._dice(table)
        assert dice is not None
        patches = []
        for die in dice:
            faces = die.props["faces"]
            assert isinstance(faces, list)
            index = table.rng.choice_index(len(faces))
            die.props = {**die.props, "value": faces[index]}
            patches.append(_piece_patch(die))
        return patches


@dataclass(frozen=True)
class SetProp:
    """Set one arbitrary property on a piece (a note's text, a die's value)."""

    piece_id: str
    key: str
    value: object
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        return _reason_not_movable(table, piece, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        piece.props = {**piece.props, self.key: self.value}
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class SetText:
    """Write on a note, token or marker: a name, a proposal, a label.

    The text is seen by whoever may see the piece's face. It is plain text;
    clients draw it with ``textContent``. An empty string wipes it.
    """

    piece_id: str
    text: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        if piece.kind not in (PieceKind.NOTE, PieceKind.TOKEN, PieceKind.MARKER):
            return "You can only write on a note, a token or a marker."
        if len(self.text) > MAX_TEXT:
            return f"That is too long: at most {MAX_TEXT} characters."
        if piece.kind is PieceKind.TOKEN and (
            len(self.text.split()) > 1 or len(self.text.strip()) > MAX_TOKEN_TEXT
        ):
            return (
                f"A token holds one word or number, at most {MAX_TOKEN_TEXT} "
                "characters."
            )
        return _reason_not_movable(table, piece, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        text = self.text.strip()
        props = {k: v for k, v in piece.props.items() if k != "text"}
        if text:
            props["text"] = text
        piece.props = props
        return [_piece_patch(piece)]


# -- locking, grouping ---------------------------------------------------------


@dataclass(frozen=True)
class Lock:
    """Lock a piece in place, so that nobody moves it by accident.

    Anyone who could move the piece may lock it, and anyone who could move
    it but for the lock may unlock it; the facilitator may do either to any
    piece. While it is locked, only the facilitator moves it.
    """

    piece_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        return _reason_out_of_reach(table, piece, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        piece.locked = True
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class Unlock:
    """Unlock a locked piece. Allowed to whoever could otherwise move it."""

    piece_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        return _reason_out_of_reach(table, piece, actor_seat)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        piece.locked = False
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class Group:
    """Tag pieces as belonging together, so they can later be moved as one."""

    piece_ids: tuple[str, ...]
    group_id: str = field(default_factory=new_op_id)
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if len(self.piece_ids) < 2:
            return "A group needs at least two pieces."
        for piece_id in self.piece_ids:
            piece = _get_piece(table, piece_id)
            if (reason := _reason_piece_missing(piece, piece_id)) is not None:
                return reason
            assert piece is not None
            if (reason := _reason_not_movable(table, piece, actor_seat)) is not None:
                return reason
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        patches = []
        for piece_id in self.piece_ids:
            piece = table.pieces[piece_id]
            piece.group_id = self.group_id
            patches.append(_piece_patch(piece))
        return patches


@dataclass(frozen=True)
class Ungroup:
    """Remove the shared group tag from a set of pieces."""

    piece_ids: tuple[str, ...]
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        for piece_id in self.piece_ids:
            reason = _reason_piece_missing(_get_piece(table, piece_id), piece_id)
            if reason is not None:
                return reason
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        patches = []
        for piece_id in self.piece_ids:
            piece = table.pieces[piece_id]
            piece.group_id = None
            patches.append(_piece_patch(piece))
        return patches


# -- pointing and ink -----------------------------------------------------------


@dataclass(frozen=True)
class Point:
    """Place a transient, named pointer ping. Nothing stored on the table changes."""

    x: float
    y: float
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if actor_seat not in table.seats:
            return "Only a seated participant may point."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        return [
            Patch(
                kind="table",
                op="event",
                entity_id=None,
                fields={
                    "type": "point",
                    "seat_id": actor_seat,
                    "x": self.x,
                    "y": self.y,
                },
            )
        ]


@dataclass(frozen=True)
class InkBegin:
    """Start a new ink stroke in the actor's own seat colour."""

    stroke_id: str
    colour: str
    width: float
    x: float
    y: float
    created_at: float = 0.0
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if actor_seat not in table.seats:
            return "Only a seated participant may draw."
        if self.stroke_id in table.strokes:
            return f"Stroke {self.stroke_id!r} already exists."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        stroke = Stroke(
            id=self.stroke_id,
            seat_id=actor_seat,
            colour=self.colour,
            width=self.width,
            points=[(self.x, self.y)],
            created_at=self.created_at,
        )
        table.strokes[stroke.id] = stroke
        return [_stroke_patch(stroke)]


@dataclass(frozen=True)
class InkAppend:
    """Add one more point to a stroke still being drawn."""

    stroke_id: str
    x: float
    y: float
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        stroke = table.strokes.get(self.stroke_id)
        if stroke is None:
            return f"There is no stroke {self.stroke_id!r} on the table."
        if stroke.seat_id != actor_seat:
            return "You may only draw your own stroke."
        if stroke.closed:
            return "That stroke has already ended."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        stroke = table.strokes[self.stroke_id]
        stroke.points.append((self.x, self.y))
        return [_stroke_patch(stroke)]


@dataclass(frozen=True)
class InkEnd:
    """Finish a stroke. It persists on the table until erased."""

    stroke_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        stroke = table.strokes.get(self.stroke_id)
        if stroke is None:
            return f"There is no stroke {self.stroke_id!r} on the table."
        if stroke.seat_id != actor_seat:
            return "You may only end your own stroke."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        stroke = table.strokes[self.stroke_id]
        stroke.closed = True
        return [_stroke_patch(stroke)]


@dataclass(frozen=True)
class EraseInk:
    """Remove a stroke: its own seat always may, and the facilitator may erase any."""

    stroke_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        stroke = table.strokes.get(self.stroke_id)
        if stroke is None:
            return f"There is no stroke {self.stroke_id!r} on the table."
        if stroke.seat_id != actor_seat and not table.is_facilitator(actor_seat):
            return "You may only erase your own ink."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        stroke = table.strokes.pop(self.stroke_id)
        return [Patch(kind="stroke", op="remove", entity_id=stroke.id, fields={})]


@dataclass(frozen=True)
class ClearInk:
    """Erase every stroke a seat has drawn, or, for the facilitator, everyone's."""

    everyone: bool = False
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        # The room itself (an activity's or a room's button acting for it) may too.
        if actor_seat not in table.seats and actor_seat != SYSTEM_SEAT:
            return "Only a seated participant may clear ink."
        if self.everyone and not table.is_facilitator(actor_seat):
            return "Only the facilitator may clear everyone's ink."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        doomed = [
            stroke_id
            for stroke_id, stroke in table.strokes.items()
            if self.everyone or stroke.seat_id == actor_seat
        ]
        for stroke_id in doomed:
            table.strokes.pop(stroke_id)
        return [
            Patch(kind="stroke", op="remove", entity_id=stroke_id, fields={})
            for stroke_id in doomed
        ]


# -- spawning and resetting -----------------------------------------------------


@dataclass(frozen=True)
class Spawn:
    """Create new pieces of one component into a zone."""

    component_id: str
    kind: PieceKind
    zone_id: str
    count: int = 1
    piece_ids: tuple[str, ...] | None = None
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if self.count < 1:
            return "Cannot spawn fewer than one piece."
        zone = _get_zone(table, self.zone_id)
        if zone is None:
            return f"There is no zone {self.zone_id!r} on the table."
        if (reason := _reason_not_for_hand(self.kind, zone)) is not None:
            return reason
        if self.piece_ids is not None:
            if len(self.piece_ids) != self.count:
                return "The number of piece ids must match the count."
            for piece_id in self.piece_ids:
                if piece_id in table.pieces:
                    return f"Piece {piece_id!r} already exists."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        zone = table.zones[self.zone_id]
        # A hidden zone is a mystery pile - spawn face-down into it. Every
        # other zone already gates who can see the face, so there is no need
        # to also start the piece face-down; a game definition that wants a
        # face-down start elsewhere can follow Spawn with Flip.
        face_up_default = zone.visibility is not Visibility.HIDDEN
        patches = []
        for offset in range(self.count):
            if self.piece_ids is not None:
                piece_id = self.piece_ids[offset]
            else:
                piece_id = new_op_id()
            index = len(table.pieces_in_zone(zone.id))
            x, y, rotation = place_in_zone(zone, index=index, count=index + 1)
            piece = Piece(
                id=piece_id,
                kind=self.kind,
                component_id=self.component_id,
                zone_id=zone.id,
                x=x,
                y=y,
                z=table.next_z_in_zone(zone.id),
                rotation=rotation,
                face_up=face_up_default,
            )
            table.pieces[piece.id] = piece
            patches.append(_piece_patch(piece))
        return patches


@dataclass(frozen=True)
class Despawn:
    """Remove pieces from the table entirely. Facilitator-only to invoke."""

    piece_ids: tuple[str, ...]
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if not table.is_facilitator(actor_seat):
            return "Only the facilitator may remove a piece from the table."
        for piece_id in self.piece_ids:
            if piece_id not in table.pieces:
                return f"There is no piece {piece_id!r} on the table."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        patches = []
        for piece_id in self.piece_ids:
            table.pieces.pop(piece_id)
            patches.append(
                Patch(kind="piece", op="remove", entity_id=piece_id, fields={})
            )
        return patches


@dataclass(frozen=True)
class ResetZone:
    """Despawn every piece currently in one zone. Facilitator-only, like Despawn."""

    zone_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if _get_zone(table, self.zone_id) is None:
            return f"There is no zone {self.zone_id!r} on the table."
        if not table.is_facilitator(actor_seat):
            return "Only the facilitator may clear a zone."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece_ids = tuple(piece.id for piece in table.pieces_in_zone(self.zone_id))
        if not piece_ids:
            return []
        return Despawn(piece_ids=piece_ids, op_id=new_op_id()).apply(table, actor_seat)


@dataclass(frozen=True)
class ResetTable:
    """Clear every piece and stroke. Zones and seats remain. Facilitator-only."""

    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if not table.is_facilitator(actor_seat):
            return "Only the facilitator may reset the table."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        patches = []
        for offer_id in list(table.offers):
            table.offers.pop(offer_id)
            patches.append(
                Patch(kind="offer", op="remove", entity_id=offer_id, fields={})
            )
        table.swapped.clear()
        for piece_id in list(table.pieces):
            table.pieces.pop(piece_id)
            patches.append(
                Patch(kind="piece", op="remove", entity_id=piece_id, fields={})
            )
        for stroke_id in list(table.strokes):
            table.strokes.pop(stroke_id)
            patches.append(
                Patch(kind="stroke", op="remove", entity_id=stroke_id, fields={})
            )
        return patches


# -- deliberate reveals ---------------------------------------------------------


@dataclass(frozen=True)
class ShowTo:
    """Reveal a piece's true face to named seats, or to everyone if none are named.

    A deliberate reveal, distinct from playing a card: the piece does not
    move and its zone does not change. Pair with ``EndShow`` to put it away
    again once whoever is showing it stops holding it up.

    Only someone whose zone already lets them see the face may show it. A
    reveal overrides the zone's visibility, so without that check anyone
    could "show" themselves a card in someone else's hand. Being shown a card
    does not count: you may not pass on what you were only shown.
    """

    piece_id: str
    seat_ids: tuple[str, ...] = ()
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        zone = table.zones.get(piece.zone_id)
        if zone is None or not entitled_to_face(
            table, piece, zone, actor_seat, count_reveals=False
        ):
            return "You can only show a piece whose face you can see."
        if piece.props.get("revealable") is False:
            return "This card is never shown to anyone."
        if piece.revealed_by is not None and piece.revealed_by != actor_seat:
            return "Someone else is already showing that piece."
        for seat_id in self.seat_ids:
            if seat_id not in table.seats:
                return f"There is no seat {seat_id!r} at the table."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        if self.seat_ids:
            piece.revealed_to = frozenset(self.seat_ids)
        else:
            piece.revealed_to = frozenset(table.seats)
        piece.revealed_by = actor_seat
        return [
            _piece_patch(piece),
            Patch(
                kind="table",
                op="event",
                entity_id=None,
                fields={
                    "type": "show",
                    "piece_id": piece.id,
                    "by_seat": actor_seat,
                    "to_seats": sorted(piece.revealed_to),
                },
            ),
        ]


@dataclass(frozen=True)
class EndShow:
    """Put away a piece shown with ``ShowTo``, restoring its zone's usual visibility.

    The person showing it may put it away, and so may the facilitator.
    """

    piece_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        if not piece.revealed_to:
            return "That piece is not being shown."
        if piece.revealed_by not in (None, actor_seat) and not table.is_facilitator(
            actor_seat
        ):
            return "Only the person showing that piece may put it away."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        shown_by = piece.revealed_by
        _clear_reveal(piece)
        return [
            _piece_patch(piece),
            Patch(
                kind="table",
                op="event",
                entity_id=None,
                fields={"type": "show_end", "piece_id": piece.id, "by_seat": shown_by},
            ),
        ]


@dataclass(frozen=True)
class Peek:
    """Look privately at a piece you can already see. Changes nothing; only logged."""

    piece_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        assert piece is not None
        zone = table.zones.get(piece.zone_id)
        if zone is None or not entitled_to_face(table, piece, zone, actor_seat):
            return "You are not entitled to see that piece's face."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        return [
            Patch(
                kind="table",
                op="event",
                entity_id=None,
                fields={
                    "type": "peek",
                    "piece_id": self.piece_id,
                    "by_seat": actor_seat,
                },
            )
        ]


# -- seats, zones, and transactions ----------------------------------------------
#
# None of these is a client intent: the realtime layer's table of wire
# operations does not include them. Seats and zones are added by the room
# service when someone sits down, and a transaction is how an exercise's
# macro is applied.


def _zone_patch(zone: Zone) -> Patch:
    geometry: dict[str, object]
    if isinstance(zone.geometry, Rect):
        geometry = {
            "shape": "rect",
            "x": zone.geometry.x,
            "y": zone.geometry.y,
            "width": zone.geometry.width,
            "height": zone.geometry.height,
        }
    else:
        geometry = {
            "shape": "polygon",
            "points": [list(point) for point in zone.geometry.points],
        }
    return Patch(
        kind="zone",
        op="upsert",
        entity_id=zone.id,
        fields={
            "kind": str(zone.kind),
            "label": zone.label,
            "geometry": geometry,
            "visibility": str(zone.visibility),
            "layout": str(zone.layout),
            "owner_seat": zone.owner_seat,
            "owner_moves_only": zone.owner_moves_only,
        },
    )


@dataclass(frozen=True)
class AddSeat:
    """Add an empty or occupied seat to the table."""

    seat_id: str
    label: str
    tint_index: int
    is_facilitator: bool = False
    participant_id: str | None = None
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if self.seat_id in table.seats:
            return f"There is already a seat {self.seat_id!r} at the table."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        seat = Seat(
            id=self.seat_id,
            label=self.label,
            tint_index=self.tint_index,
            participant_id=self.participant_id,
            is_facilitator=self.is_facilitator,
        )
        table.seats[seat.id] = seat
        return [
            Patch(
                kind="seat",
                op="upsert",
                entity_id=seat.id,
                fields={
                    "label": seat.label,
                    "tint_index": seat.tint_index,
                    "participant_id": seat.participant_id,
                    "is_facilitator": seat.is_facilitator,
                },
            )
        ]


@dataclass(frozen=True)
class AssignSeat:
    """Set who sits in a seat, or empty it. Only the room service issues this."""

    seat_id: str
    participant_id: str | None
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if self.seat_id not in table.seats:
            return f"There is no seat {self.seat_id!r} at the table."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        seat = table.seats[self.seat_id]
        seat.participant_id = self.participant_id
        return [
            Patch(
                kind="seat",
                op="upsert",
                entity_id=seat.id,
                fields={"participant_id": seat.participant_id},
            )
        ]


@dataclass(frozen=True)
class AddZone:
    """Add a zone to the table: at setup, or when a seat brings its own hand."""

    zone_id: str
    kind: ZoneKind
    label: str
    geometry: Rect | Polygon
    visibility: Visibility
    layout: Layout
    owner_seat: str | None = None
    capacity: int | None = None
    owner_moves_only: bool = False
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if self.zone_id in table.zones:
            return f"There is already a zone {self.zone_id!r} on the table."
        if self.owner_seat is not None and self.owner_seat not in table.seats:
            return f"There is no seat {self.owner_seat!r} at the table."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        geometry: Geometry = self.geometry
        zone = Zone(
            id=self.zone_id,
            kind=self.kind,
            label=self.label,
            geometry=geometry,
            visibility=self.visibility,
            layout=self.layout,
            owner_seat=self.owner_seat,
            capacity=self.capacity,
            owner_moves_only=self.owner_moves_only,
        )
        table.zones[zone.id] = zone
        return [_zone_patch(zone)]


@dataclass(frozen=True)
class RemoveZone:
    """Take an empty zone off the table: one added while the room was in use.

    Facilitator-only, like clearing a zone. A zone with pieces in it, or one
    an activity laid out, is refused: emptying it and ending the activity
    are their own operations.
    """

    zone_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        zone = _get_zone(table, self.zone_id)
        if zone is None:
            return f"There is no zone {self.zone_id!r} on the table."
        if not table.is_facilitator(actor_seat):
            return "Only the facilitator may remove a zone."
        if table.pieces_in_zone(zone.id):
            return f"{zone.label} still has pieces in it."
        if any(zone.id in activity.zones for activity in table.activities.values()):
            return f"{zone.label} belongs to an activity."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        del table.zones[self.zone_id]
        return [Patch(kind="zone", op="remove", entity_id=self.zone_id, fields={})]


@dataclass(frozen=True)
class Transaction:
    """Several operations applied as one: every one of them, or none at all.

    ``validate`` runs the steps in order against a copy of the table, so a
    step is judged against what the steps before it did, and the first
    reason any of them gives is the transaction's reason. ``apply`` then runs
    the same steps against the real table. Because the copy carries the
    table's RNG state, a shuffle or a roll lands the same way both times.

    ``name`` says what the transaction is for the event log (``macro:deal``,
    ``setup``, ``seat:seat-3``); ``label`` is the same thing for a person.
    No steps at all is a valid transaction that changes nothing.
    """

    steps: tuple[Operation, ...]
    name: str = ""
    label: str = ""
    op_id: str = field(default_factory=new_op_id)
    system: bool = False
    activity_id: str = ""
    """The activity a button was pressed in, or "" outside one; for the log."""

    def validate(self, table: Table, actor_seat: str) -> str | None:
        trial = copy.deepcopy(table)
        actor = SYSTEM_SEAT if self.system else actor_seat
        for step in self.steps:
            reason = step.validate(trial, actor)
            if reason is not None:
                return reason
            step.apply(trial, actor)
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        patches: list[Patch] = []
        actor = SYSTEM_SEAT if self.system else actor_seat
        for step in self.steps:
            patches.extend(step.apply(table, actor))
        return patches
