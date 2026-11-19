"""A hand holds cards and tokens, nothing else."""

import pytest
from _model_support import (
    DECK,
    HAND_A,
    HAND_B,
    PUBLIC_TABLE,
    SEAT_A,
    build_die,
    build_sample_table,
)

from sandbox.model.entities import Piece
from sandbox.model.ops import Deal, Draw, MoveToZone, Spawn, StackOnto, run_op
from sandbox.model.results import Ok, Reject
from sandbox.model.types import PieceKind

REFUSAL = "Only cards and tokens go in a hand."


def _piece(piece_id: str, kind: PieceKind, zone_id: str = PUBLIC_TABLE) -> Piece:
    return Piece(
        id=piece_id,
        kind=kind,
        component_id=f"{kind}-1",
        zone_id=zone_id,
        x=10,
        y=10,
        z=0,
        face_up=True,
    )


@pytest.mark.parametrize("kind", [PieceKind.CARD, PieceKind.TOKEN])
def test_a_card_or_token_goes_into_a_hand(kind: PieceKind) -> None:
    table = build_sample_table(deck_size=0)
    table.pieces["p"] = _piece("p", kind)

    outcome = run_op(table, SEAT_A, MoveToZone(piece_id="p", zone_id=HAND_A))

    assert isinstance(outcome, Ok)
    assert table.pieces["p"].zone_id == HAND_A


OTHER_KINDS = [
    PieceKind.DIE,
    PieceKind.CUBE,
    PieceKind.MEEPLE,
    PieceKind.NOTE,
    PieceKind.TILE,
]


@pytest.mark.parametrize("kind", OTHER_KINDS)
def test_anything_else_is_refused_by_a_hand(kind: PieceKind) -> None:
    table = build_sample_table(deck_size=0)
    table.pieces["p"] = _piece("p", kind)

    outcome = run_op(table, SEAT_A, MoveToZone(piece_id="p", zone_id=HAND_A))

    assert outcome == Reject(REFUSAL)
    assert table.pieces["p"].zone_id == PUBLIC_TABLE


def test_a_die_cannot_be_stacked_onto_a_card_in_a_hand() -> None:
    table = build_sample_table(deck_size=1)
    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=HAND_A))
    table.pieces["die-1"] = build_die()

    outcome = run_op(table, SEAT_A, StackOnto(piece_id="die-1", onto_id="card-0"))

    assert outcome == Reject(REFUSAL)


def test_a_die_cannot_be_spawned_drawn_or_dealt_into_a_hand() -> None:
    table = build_sample_table(deck_size=0)
    assert run_op(
        table, SEAT_A, Spawn(component_id="d6", kind=PieceKind.DIE, zone_id=HAND_A)
    ) == Reject(REFUSAL)

    table.pieces["die-1"] = build_die(zone_id=DECK)
    draw = Draw(count=1, from_zone=DECK, to_zone=HAND_A)
    assert run_op(table, SEAT_A, draw) == Reject(REFUSAL)
    assert run_op(
        table, SEAT_A, Deal(from_zone=DECK, to_zones=(HAND_A,), count_each=1)
    ) == Reject(REFUSAL)
    assert table.pieces["die-1"].zone_id == DECK


def test_a_deal_is_refused_only_when_a_die_would_reach_a_hand() -> None:
    table = build_sample_table(deck_size=2)
    # A die at the bottom of the pile, below both cards: dealing one each
    # takes only the cards.
    table.pieces["die-1"] = build_die(zone_id=DECK)
    table.pieces["die-1"].z = -1

    deal = Deal(from_zone=DECK, to_zones=(HAND_A, HAND_B), count_each=1)
    assert isinstance(run_op(table, SEAT_A, deal), Ok)
    assert table.pieces["die-1"].zone_id == DECK
