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

from sandbox.model.entities import Piece, Table, Zone
from sandbox.model.ops import (
    Deal,
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
    Shuffle,
    Unlock,
)
from sandbox.model.types import PieceKind, Visibility, ZoneKind
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


# How many cards each the deck menu offers to deal to everyone at once.
DEAL_COUNTS = (1, 3, 5)


def _players_hands(table: Table, deck: Zone) -> list[str]:
    """The private hands a deck deals to: one per player, in seat order.

    Only a private hand counts, so what each player is dealt is theirs alone.
    A deck on the room's own table deals to the room's hands. A deck that
    belongs to an activity deals to that activity's private hands if it has
    them, and otherwise to its players' hands in the room. A hand counts
    when someone is sitting in its seat and that someone is not the
    facilitator, who does not play.
    """
    activity = next((a for a in table.activities.values() if deck.id in a.zones), None)
    in_activities = {z for a in table.activities.values() for z in a.zones}
    hands = [
        zone
        for zone in table.zones.values()
        if zone.kind is ZoneKind.HAND
        and zone.visibility is Visibility.PRIVATE_TO_OWNER
        and zone.owner_seat is not None
        and (seat := table.seats.get(zone.owner_seat)) is not None
        and seat.participant_id is not None
        and not seat.is_facilitator
    ]
    room_hands = [zone for zone in hands if zone.id not in in_activities]
    if activity is None:
        chosen = room_hands
    else:
        own = [zone for zone in hands if zone.id in activity.zones]
        chosen = own or [z for z in room_hands if z.owner_seat in activity.seats]
    order = list(table.seats)
    chosen.sort(key=lambda zone: order.index(zone.owner_seat or ""))
    return [zone.id for zone in chosen]


def _deck_entries(table: Table, piece: Piece) -> list[MenuEntry]:
    """Shuffling a deck, and dealing from it to everyone, from any card in it."""
    deck = table.zones.get(piece.zone_id)
    if deck is None or deck.kind is not ZoneKind.DECK:
        return []
    entries = [MenuEntry("shuffle", "Shuffle the deck", Shuffle(zone_id=deck.id))]
    hands = tuple(_players_hands(table, deck))
    if not hands:
        return entries
    # Besides the usual few, as many each as go round, so a deck can be
    # dealt out evenly in one go.
    most = len(table.pieces_in_zone(deck.id)) // len(hands)
    for count in sorted({*DEAL_COUNTS, most}):
        label = "1 card each" if count == 1 else f"{count} cards each"
        if count == most and count not in DEAL_COUNTS:
            label = f"{label}, as many as go round"
        entries.append(
            MenuEntry(
                f"deal:{count}",
                label,
                # Face up, so each player can read what they were dealt: in a
                # private hand that is its owner alone.
                Deal(from_zone=deck.id, to_zones=hands, count_each=count, face_up=True),
                group="Deal to everyone…",
            )
        )
    return entries


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
    entries.extend(_deck_entries(table, piece))

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
