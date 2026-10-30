"""Value Cards Trading's escape hatch: calling time.

Calling time ends trading and keeps a record of every hand as it stands.
It never blocks: a pair that has not traded yet is named in the record and
in the table's announcement, and the group decides what to do about it.
"""

from __future__ import annotations

from sandbox.games.hatch import GameContext, MacroRefused, macro
from sandbox.model import CloseOffers, Operation, Record, Table

HAND = "hand"


def untraded_pairs(table: Table, seats: tuple[str, ...]) -> list[tuple[str, str]]:
    """Each pair of seats that has not yet completed a swap, in seat order."""
    return [
        (first, second)
        for index, first in enumerate(seats)
        for second in seats[index + 1 :]
        if frozenset((first, second)) not in table.swapped
    ]


@macro("call_time")
def call_time(table: Table, context: GameContext) -> list[Operation]:
    """Close open offers and record each seat's hand and who has not traded."""
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
        CloseOffers(),
        Record(
            label="call_time",
            data={
                "hands": {labels[seat]: cards for seat, cards in hands.items()},
                "not_yet_traded": untraded,
            },
        ),
    ]
