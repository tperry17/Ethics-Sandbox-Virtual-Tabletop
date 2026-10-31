"""Value Cards Trading's escape hatch: recording the hands.

Trading has no time limit, so nothing here ends it. Recording keeps what
every hand holds, and which pairs have not yet traded, in the permanent
log, for the debrief. It never blocks: pressing it again records again.
"""

from __future__ import annotations

from sandbox.games.hatch import GameContext, MacroRefused, macro
from sandbox.model import Operation, Record, Table

HAND = "hand"


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
