"""Table operations: the only way a Table may change.

Each operation is a small, self-contained request: it carries its own
payload as fields, knows how to validate itself against the current table,
and knows how to apply itself. Never call ``apply`` directly - call
``run_op``, which enforces idempotency by operation id and advances the
table's version, so a retried message is harmless.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from sandbox.model.entities import Piece, Stroke, Table, Zone
from sandbox.model.layout import place_in_zone
from sandbox.model.results import Ok, OpOutcome, Patch, Reject
from sandbox.model.types import PieceKind, Visibility
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
    table.applied_op_ids.add(op.op_id)
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
    """Shared legality check for grabbing, moving, flipping, and rotating."""
    if piece.locked and not table.is_facilitator(actor_seat):
        return "That piece is locked."
    if piece.held_by is not None and piece.held_by != actor_seat:
        return "Someone else is already holding that piece."
    return None


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
        },
    )


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
        piece.x, piece.y = self.x, self.y
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class MoveToZone:
    """Move a piece into a different zone, atomically re-placing it there.

    If ``x``/``y`` are omitted, the destination zone's layout decides where
    the piece lands. Because this is one operation, a piece moving into a
    private zone never passes through an intermediate state where its true
    face is visible to someone not entitled to it.
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
        piece.zone_id = zone.id
        piece.z = table.next_z_in_zone(zone.id)
        piece.revealed_to = frozenset()
        if self.x is not None and self.y is not None:
            piece.x, piece.y, piece.rotation = self.x, self.y, piece.rotation
        else:
            index = len(table.pieces_in_zone(zone.id)) - 1
            x, y, rotation = place_in_zone(zone, index=index, count=index + 1)
            piece.x, piece.y, piece.rotation = x, y, rotation
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
        return _reason_not_movable(table, piece, actor_seat)

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
    """Shuffle the pieces within a zone into a new order, using the table's RNG."""

    zone_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if _get_zone(table, self.zone_id) is None:
            return f"There is no zone {self.zone_id!r} on the table."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        pieces = table.pieces_in_zone(self.zone_id)
        if len(pieces) <= 1:
            return []
        z_values = [piece.z for piece in pieces]
        order = table.rng.shuffled_indices(len(pieces))
        for piece, z in zip(pieces, (z_values[i] for i in order), strict=True):
            piece.z = z
        return [_piece_patch(piece) for piece in pieces]


@dataclass(frozen=True)
class Draw:
    """Move the top ``count`` pieces of one zone into another."""

    count: int
    from_zone: str
    to_zone: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if self.count < 1:
            return "Cannot draw fewer than one piece."
        source = _get_zone(table, self.from_zone)
        if source is None:
            return f"There is no zone {self.from_zone!r} on the table."
        if _get_zone(table, self.to_zone) is None:
            return f"There is no zone {self.to_zone!r} on the table."
        available = table.pieces_in_zone(self.from_zone)
        if len(available) < self.count:
            return f"Only {len(available)} pieces remain in {source.label}."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        destination = table.zones[self.to_zone]
        drawn = table.pieces_in_zone(self.from_zone)[-self.count :]
        patches = []
        for piece in drawn:
            next_z = table.next_z_in_zone(destination.id)
            index = len(table.pieces_in_zone(destination.id))
            piece.zone_id = destination.id
            piece.z = next_z
            x, y, rotation = place_in_zone(destination, index=index, count=index + 1)
            piece.x, piece.y, piece.rotation = x, y, rotation
            piece.revealed_to = frozenset()
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
        available = len(table.pieces_in_zone(self.from_zone))
        if available < needed:
            return (
                f"Only {available} pieces remain in {source.label}, "
                f"but dealing needs {needed}."
            )
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        patches: list[Patch] = []
        for _round in range(self.count_each):
            for zone_id in self.to_zones:
                draw = Draw(
                    count=1,
                    from_zone=self.from_zone,
                    to_zone=zone_id,
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


# -- locking, grouping ---------------------------------------------------------


@dataclass(frozen=True)
class Lock:
    """Lock a piece so only the facilitator may move it. Facilitator-only to invoke."""

    piece_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        if not table.is_facilitator(actor_seat):
            return "Only the facilitator may lock a piece."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        piece.locked = True
        return [_piece_patch(piece)]


@dataclass(frozen=True)
class Unlock:
    """Unlock a previously locked piece. Facilitator-only to invoke."""

    piece_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
        if not table.is_facilitator(actor_seat):
            return "Only the facilitator may unlock a piece."
        return None

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
        if _get_zone(table, self.zone_id) is None:
            return f"There is no zone {self.zone_id!r} on the table."
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
    """Remove pieces from the table entirely."""

    piece_ids: tuple[str, ...]
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
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
    """Despawn every piece currently in one zone."""

    zone_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if _get_zone(table, self.zone_id) is None:
            return f"There is no zone {self.zone_id!r} on the table."
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
    """

    piece_id: str
    seat_ids: tuple[str, ...] = ()
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        if (reason := _reason_piece_missing(piece, self.piece_id)) is not None:
            return reason
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
    """Put away a piece shown with ``ShowTo``, restoring its zone's usual visibility."""

    piece_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        piece = _get_piece(table, self.piece_id)
        return _reason_piece_missing(piece, self.piece_id)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        piece = table.pieces[self.piece_id]
        piece.revealed_to = frozenset()
        return [_piece_patch(piece)]


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
