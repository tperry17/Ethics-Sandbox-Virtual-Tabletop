"""Value Cards Trading's escape hatch: the deal, and recording the hands.

The deal gives every player six cards. Three play with the 18 cards of the
base deck; with four, five or six players the sidebar's 18 join the deck
first, so there are enough to go round.

Trading has no time limit, so nothing here ends it. Recording keeps what
every hand holds, and which pairs have not yet traded, in the permanent
log, for the debrief. It never blocks: pressing it again records again.
"""

from __future__ import annotations

from sandbox.games.hatch import GameContext, MacroRefused, macro
from sandbox.model import Deal, MoveToZone, Operation, Record, Shuffle, Table

HAND = "hand"
DECK = "deck"
SIDEBAR = "sidebar"
EACH = 6
BASE_PLAYERS = 3
"""Up to this many players use the base deck alone."""


@macro("deal_six_each")
def deal_six_each(table: Table, context: GameContext) -> list[Operation]:
    """Six open cards to every player, from the sidebar too with four or more."""
    deck = context.zone(DECK)
    operations: list[Operation] = []
    available = len(table.pieces_in_zone(deck))
    if len(context.seats) > BASE_PLAYERS:
        sidebar = table.pieces_in_zone(context.zone(SIDEBAR))
        operations += [MoveToZone(piece_id=piece.id, zone_id=deck) for piece in sidebar]
        available += len(sidebar)
        if sidebar:
            operations.append(Shuffle(zone_id=deck))
    if available < EACH * len(context.seats):
        raise MacroRefused(
            "There are not enough cards in the deck to deal six each. "
            "Collect the cards first."
        )
    operations.append(
        Deal(
            from_zone=deck,
            to_zones=context.seat_zones(HAND),
            count_each=EACH,
            face_up=True,
        )
    )
    return operations


def untraded_pairs(table: Table, seats: tuple[str, ...]) -> list[tuple[str, str]]:
    """Each pair of seats that has not yet completed a swap, in seat order."""
    return [
        (first, second)
        for index, first in enumerate(seats)
        for second in seats[index + 1 :]
        if frozenset((first, second)) not in table.swapped
    ]


@macro("record_hands")
def record_hands(table: Table, context: GameContext) -> list[Operation]:
    """Keep every seat's hand and who has not traded yet."""
    hands = {
        seat: [
            piece.component_id
            for piece in table.pieces_in_zone(context.zone(HAND, seat))
        ]
        for seat in context.seats
    }
    if not any(hands.values()):
        raise MacroRefused("Nobody holds any cards yet. Deal first.")
    labels = {seat: table.seats[seat].label for seat in context.seats}
    untraded = [
        f"{labels[first]} and {labels[second]}"
        for first, second in untraded_pairs(table, context.seats)
    ]
    return [
        Record(
            label="record_hands",
            data={
                "hands": {labels[seat]: cards for seat, cards in hands.items()},
                "not_yet_traded": untraded,
            },
        )
    ]
