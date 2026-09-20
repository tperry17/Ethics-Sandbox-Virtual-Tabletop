"""The single security boundary: what one viewer is entitled to know about a table.

Everything sent to a browser must pass through ``project``. A face-down
card, or a card in someone else's hand, comes back with its ``component_id``
stripped: there is a back to draw and nothing else. Test this adversarially.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sandbox.model.entities import Piece, Table, Zone
from sandbox.model.results import Patch
from sandbox.model.types import PieceKind, Visibility


@dataclass(frozen=True)
class ViewPiece:
    """A piece as one particular viewer is entitled to see it.

    ``component_id`` is present only when this viewer may see its face. When
    it is absent, ``face_up`` is always False from the viewer's perspective,
    regardless of the piece's real, private state.
    """

    id: str
    kind: PieceKind
    zone_id: str
    x: float
    y: float
    z: int
    rotation: float
    face_up: bool
    held_by: str | None
    locked: bool
    component_id: str | None


@dataclass(frozen=True)
class ViewZone:
    id: str
    label: str
    visibility: Visibility
    owner_seat: str | None


@dataclass(frozen=True)
class ViewSeat:
    id: str
    label: str
    tint_index: int
    participant_id: str | None
    is_facilitator: bool


@dataclass(frozen=True)
class ViewStroke:
    id: str
    seat_id: str
    colour: str
    width: float
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class ViewTable:
    """Everything one viewer's client is allowed to receive, and nothing else."""

    pieces: tuple[ViewPiece, ...]
    zones: tuple[ViewZone, ...]
    seats: tuple[ViewSeat, ...]
    strokes: tuple[ViewStroke, ...]
    version: int


def entitled_to_face(
    table: Table, piece: Piece, zone: Zone, viewer_seat: str | None
) -> bool:
    """Whether ``viewer_seat`` may see ``piece``'s true, current face.

    A deliberate reveal (``piece.revealed_to``) always wins. Otherwise a
    face-down piece shows its face to no one at all - there is nothing to be
    entitled to until it is turned over - and a hidden zone (a deck) shows
    its pieces' faces to no one, ever, regardless of ``face_up``: that flag
    is not to be trusted for a piece nobody has looked at yet.
    """
    if viewer_seat is not None and viewer_seat in piece.revealed_to:
        return True
    if zone.visibility is Visibility.HIDDEN:
        return False
    if not piece.face_up:
        return False
    if zone.visibility is Visibility.PUBLIC:
        return True
    if zone.visibility is Visibility.PRIVATE_TO_OWNER:
        return viewer_seat is not None and viewer_seat == zone.owner_seat
    if zone.visibility is Visibility.FACILITATOR_ONLY:
        if viewer_seat is None:
            return False
        if viewer_seat == zone.owner_seat:
            return True
        return table.is_facilitator(viewer_seat)
    return False


def _project_piece(table: Table, piece: Piece, viewer_seat: str | None) -> ViewPiece:
    zone = table.zones.get(piece.zone_id)
    entitled = zone is not None and entitled_to_face(table, piece, zone, viewer_seat)
    return ViewPiece(
        id=piece.id,
        kind=piece.kind,
        zone_id=piece.zone_id,
        x=piece.x,
        y=piece.y,
        z=piece.z,
        rotation=piece.rotation,
        face_up=piece.face_up if entitled else False,
        held_by=piece.held_by,
        locked=piece.locked,
        component_id=piece.component_id if entitled else None,
    )


def project(table: Table, viewer_seat: str | None) -> ViewTable:
    """Project ``table`` down to exactly what ``viewer_seat`` may know.

    Pass ``None`` for an anonymous spectator, entitled to nothing that is not
    public. This function is the single security boundary in the product.
    """

    def sort_key(piece: Piece) -> tuple[str, int]:
        return (piece.zone_id, piece.z)

    pieces = tuple(
        _project_piece(table, piece, viewer_seat)
        for piece in sorted(table.pieces.values(), key=sort_key)
    )
    zones = tuple(
        ViewZone(
            id=zone.id,
            label=zone.label,
            visibility=zone.visibility,
            owner_seat=zone.owner_seat,
        )
        for zone in table.zones.values()
    )
    seats = tuple(
        ViewSeat(
            id=seat.id,
            label=seat.label,
            tint_index=seat.tint_index,
            participant_id=seat.participant_id,
            is_facilitator=seat.is_facilitator,
        )
        for seat in table.seats.values()
    )
    strokes = tuple(
        ViewStroke(
            id=stroke.id,
            seat_id=stroke.seat_id,
            colour=stroke.colour,
            width=stroke.width,
            points=tuple(stroke.points),
        )
        for stroke in table.strokes.values()
    )
    return ViewTable(
        pieces=pieces,
        zones=zones,
        seats=seats,
        strokes=strokes,
        version=table.version,
    )


def project_patch(table: Table, patch: Patch, viewer_seat: str | None) -> Patch | None:
    """``patch`` as ``viewer_seat`` may receive it, or None if they may not.

    The same boundary as ``project``, applied to an increment rather than a
    whole table: a piece whose face this viewer is not entitled to loses its
    ``component_id`` and reports ``face_up`` False, and a private event -
    one person looking at their own card - is not forwarded to anyone else
    at all. Patches are projected against the table as it is now, which is
    why the realtime layer projects them immediately after applying them.
    """
    if patch.kind == "piece" and patch.op == "upsert" and patch.entity_id is not None:
        piece = table.pieces.get(patch.entity_id)
        zone = None if piece is None else table.zones.get(piece.zone_id)
        entitled = (
            piece is not None
            and zone is not None
            and entitled_to_face(table, piece, zone, viewer_seat)
        )
        fields = dict(patch.fields)
        # ``props`` never crosses this boundary as a bulk field: a game that
        # needs one on the client sends it deliberately as its own patch.
        fields.pop("props", None)
        if not entitled:
            fields["face_up"] = False
            fields["component_id"] = None
        return Patch(
            kind=patch.kind, op=patch.op, entity_id=patch.entity_id, fields=fields
        )
    is_peek = patch.kind == "table" and patch.op == "event"
    if is_peek and patch.fields.get("type") == "peek":
        by_seat = patch.fields.get("by_seat")
        if viewer_seat is None or by_seat != viewer_seat:
            return None
    return patch


def project_patches(
    table: Table, patches: Iterable[Patch], viewer_seat: str | None
) -> list[Patch]:
    """Every patch in ``patches`` this viewer is entitled to, already projected."""
    projected = (project_patch(table, patch, viewer_seat) for patch in patches)
    return [patch for patch in projected if patch is not None]
