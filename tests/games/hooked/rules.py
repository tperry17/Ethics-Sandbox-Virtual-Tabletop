"""Hooks and macros for the test-only ``hooked`` game."""

from __future__ import annotations

from sandbox.games.hatch import GameContext, MacroRefused, hook, macro
from sandbox.model import Operation, Roll, SetProp, Spawn, Table
from sandbox.model.types import PieceKind


@hook("after_setup")
def roll_after_setup(table: Table, context: GameContext) -> list[Operation]:
    dice = [piece for piece in table.pieces.values() if piece.kind is PieceKind.DIE]
    return [Roll(target_id=die.id) for die in dice]


@hook("seat_change")
def marker_for_new_seat(table: Table, context: GameContext) -> list[Operation]:
    assert context.seat_id is not None
    return [
        Spawn(
            component_id="marker",
            kind=PieceKind.TOKEN,
            zone_id=context.zone("tray", context.seat_id),
            piece_ids=(f"welcome-{context.seat_id}",),
        )
    ]


@hook("before_macro")
def note_the_macro(table: Table, context: GameContext) -> list[Operation]:
    dice = sorted(
        piece.id for piece in table.pieces.values() if piece.kind is PieceKind.DIE
    )
    if not dice:
        return []
    return [SetProp(piece_id=dice[0], key="last_macro", value=context.macro_id)]


@macro("marker_each")
def marker_each(table: Table, context: GameContext) -> list[Operation]:
    return [
        Spawn(component_id="marker", kind=PieceKind.TOKEN, zone_id=zone)
        for zone in context.seat_zones("tray")
    ]


@macro("always_refuse")
def always_refuse(table: Table, context: GameContext) -> list[Operation]:
    raise MacroRefused("Not today.")
