"""Pairs' escape hatch: catching pairs.

Catching could not be steps: which cards to move depends on what each hand
holds. It looks at every hand, takes each rank held twice, and lays those
two cards face up in the middle, in seat order. It refuses, with a reason,
when nothing has been dealt or nobody holds a pair.
"""

from __future__ import annotations

from sandbox.games.hatch import GameContext, MacroRefused, macro
from sandbox.model import Flip, MoveToZone, Operation, Piece, Table

CAUGHT = "caught"
HAND = "hand"


def rank(piece: Piece) -> str:
    """``cards:ace-of-hearts`` -> ``ace``."""
    return piece.component_id.split(":", 1)[1].split("-of-", 1)[0]


@macro("call_pairs")
def call_pairs(table: Table, context: GameContext) -> list[Operation]:
    """Every pair held, face up in the middle."""
    caught = context.zone(CAUGHT)
    operations: list[Operation] = []
    anyone_holds_cards = False
    for seat in context.seats:
        hand = table.pieces_in_zone(context.zone(HAND, seat))
        anyone_holds_cards = anyone_holds_cards or bool(hand)
        by_rank: dict[str, list[Piece]] = {}
        for piece in hand:
            by_rank.setdefault(rank(piece), []).append(piece)
        for pieces in by_rank.values():
            for piece in pieces[:2] if len(pieces) >= 2 else []:
                operations.append(MoveToZone(piece_id=piece.id, zone_id=caught))
                operations.append(Flip(piece_id=piece.id, face_up=True))
    if not anyone_holds_cards:
        raise MacroRefused("Nobody holds any cards yet. Deal first.")
    if not operations:
        raise MacroRefused("Nobody holds a pair.")
    return operations
