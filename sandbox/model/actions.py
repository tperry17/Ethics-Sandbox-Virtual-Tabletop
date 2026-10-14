"""What one seat may do to one piece, right now: the context menu's contents.

The table client cannot build its own menu. Whether a piece may be flipped,
shown, locked or sent somewhere depends on rules it does not know, so it
asks, and the answer is computed here, by offering every plausible
operation and keeping the ones whose own ``validate`` accepts them. Nothing
in this module is a rule of its own: an entry is on the menu exactly when
the operation it names would be allowed.
"""

from __future__ import annotations

from dataclasses import dataclass

from sandbox.model.entities import Piece, Table
from sandbox.model.ops import (
    Despawn,
    EndShow,
    Flip,
    Lock,
    MoveToZone,
    Operation,
    Peek,
    ReorderZ,
    Roll,
    Rotate,
    ShowTo,
    Unlock,
)
from sandbox.model.types import PieceKind, ZoneKind
from sandbox.model.visibility import entitled_to_face


@dataclass(frozen=True)
class MenuEntry:
    """One thing a seat may do to a piece.

    ``key`` is stable across requests, so a client can tell entries apart.
    ``seat_id`` names a seat the entry is about - someone to show a card to,
    or the owner of a zone to move it into - so whoever presents the menu can
    use that person's name rather than the seat's label.
    """

    key: str
    label: str
    operation: Operation
    group: str | None = None
    seat_id: str | None = None


def _entitled_by_zone(table: Table, piece: Piece, seat_id: str) -> bool:
    zone = table.zones.get(piece.zone_id)
    return zone is not None and entitled_to_face(
        table, piece, zone, seat_id, count_reveals=False
    )


def _candidates(table: Table, piece: Piece, seat_id: str) -> list[MenuEntry]:
    entries: list[MenuEntry] = [
        # "Turn over" rather than "turn face up/down": the true orientation
        # of a piece this seat cannot see is not this menu's to announce.
        MenuEntry("flip", "Turn over", Flip(piece_id=piece.id)),
        MenuEntry("rotate_cw", "Rotate clockwise", Rotate(piece_id=piece.id)),
        MenuEntry(
            "rotate_ccw",
            "Rotate anticlockwise",
            Rotate(piece_id=piece.id, degrees=-90.0),
        ),
    ]
    if piece.kind is PieceKind.DIE:
        entries.append(MenuEntry("roll", "Roll", Roll(target_id=piece.id)))

    entries.append(MenuEntry("look", "Look closely", Peek(piece_id=piece.id)))

    own_hands = [
        zone
        for zone in table.zones.values()
        if zone.kind is ZoneKind.HAND
        and zone.owner_seat == seat_id
        and zone.id != piece.zone_id
    ]
    for zone in own_hands:
        entries.append(
            MenuEntry(
                f"to_hand:{zone.id}",
                "Send to my hand",
                MoveToZone(piece_id=piece.id, zone_id=zone.id),
            )
        )

    if piece.revealed_to:
        entries.append(
            MenuEntry("end_show", "Stop showing", EndShow(piece_id=piece.id))
        )
    elif _entitled_by_zone(table, piece, seat_id):
        others = [
            seat
            for seat in table.seats.values()
            if seat.id != seat_id and not _entitled_by_zone(table, piece, seat.id)
        ]
        if others:
            entries.append(
                MenuEntry("show_table", "Show to the table", ShowTo(piece_id=piece.id))
            )
        for seat in others:
            entries.append(
                MenuEntry(
                    f"show_to:{seat.id}",
                    seat.label,
                    ShowTo(piece_id=piece.id, seat_ids=(seat.id,)),
                    group="Show to…",
                    seat_id=seat.id,
                )
            )

    if len(table.pieces_in_zone(piece.zone_id)) > 1:
        entries.append(
            MenuEntry("top", "Move to top", ReorderZ(piece_id=piece.id, to_top=True))
        )
        entries.append(
            MenuEntry(
                "bottom", "Move to bottom", ReorderZ(piece_id=piece.id, to_top=False)
            )
        )

    own_hand_ids = {zone.id for zone in own_hands}
    for zone in table.zones.values():
        if zone.id == piece.zone_id or zone.id in own_hand_ids:
            continue
        entries.append(
            MenuEntry(
                f"move:{zone.id}",
                zone.label,
                MoveToZone(piece_id=piece.id, zone_id=zone.id),
                group="Move to…",
                seat_id=zone.owner_seat,
            )
        )

    if piece.locked:
        entries.append(MenuEntry("unlock", "Unlock", Unlock(piece_id=piece.id)))
    else:
        entries.append(MenuEntry("lock", "Lock in place", Lock(piece_id=piece.id)))
    entries.append(
        MenuEntry("delete", "Remove from the table", Despawn(piece_ids=(piece.id,)))
    )
    return entries


def piece_actions(table: Table, piece_id: str, seat_id: str) -> list[MenuEntry]:
    """Every entry ``seat_id`` may use on ``piece_id`` now, in menu order.

    An empty list means there is nothing this seat may do to that piece -
    including when the piece or the seat does not exist.
    """
    piece = table.pieces.get(piece_id)
    if piece is None or seat_id not in table.seats:
        return []
    return [
        entry
        for entry in _candidates(table, piece, seat_id)
        if entry.operation.validate(table, seat_id) is None
    ]
