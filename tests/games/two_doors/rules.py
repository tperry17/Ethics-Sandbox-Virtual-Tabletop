"""Two Doors' escape hatch: the Reveal macro.

Revealing could almost be steps - move each hand to the doors, turn them
up - but it should refuse, with a reason, when a seat has nothing to show
or the doors are already taken, and it should lay the cards out in seat
order. That is what Python is for here.
"""

from __future__ import annotations

from sandbox.games.hatch import GameContext, MacroRefused, macro
from sandbox.model import Flip, MoveToZone, Operation, Table

DOORS = "doors"
HAND = "hand"


@macro("reveal")
def reveal(table: Table, context: GameContext) -> list[Operation]:
    """Each seat's card, in seat order, face up on the doors."""
    if table.pieces_in_zone(DOORS):
        raise MacroRefused("The doors already hold cards. Collect them first.")
    operations: list[Operation] = []
    for seat in context.seats:
        hand = table.pieces_in_zone(context.zone(HAND, seat))
        if not hand:
            label = table.seats[seat].label
            raise MacroRefused(f"{label} has no card to reveal. Deal first.")
        card = hand[-1]
        operations.append(MoveToZone(piece_id=card.id, zone_id=DOORS))
        operations.append(Flip(piece_id=card.id, face_up=True))
    return operations
