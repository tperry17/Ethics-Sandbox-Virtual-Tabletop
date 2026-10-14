"""The operations the table client's interaction half leans on.

Reveals are a speech act in these exercises, so who may make one - and who
may pass on what they were only shown - is tested here as carefully as
``project`` itself. Stacking, dropping into a laid-out zone, and clearing
ink are the other gestures that needed the model's help.
"""

from __future__ import annotations

from _model_support import (
    DECK,
    DISCARD,
    FACILITATOR,
    HAND_A,
    HAND_B,
    PUBLIC_TABLE,
    SEAT_A,
    SEAT_B,
    build_sample_table,
)

from sandbox.db.snapshot import from_snapshot, to_snapshot
from sandbox.model.entities import Table
from sandbox.model.ops import (
    ClearInk,
    Despawn,
    EndShow,
    InkBegin,
    Move,
    MoveToZone,
    ShowTo,
    StackOnto,
    run_op,
)
from sandbox.model.results import Ok, Reject
from sandbox.model.visibility import project


def _card_in_hand_a(table: Table, piece_id: str = "card-0") -> str:
    table.pieces[piece_id].zone_id = HAND_A
    table.pieces[piece_id].face_up = True
    return piece_id


def _face(table: Table, viewer: str, piece_id: str) -> str | None:
    view = next(p for p in project(table, viewer).pieces if p.id == piece_id)
    return view.component_id


# -- who may show a card ---------------------------------------------------------


def test_nobody_may_show_themselves_a_card_in_someone_elses_hand() -> None:
    table = build_sample_table(deck_size=1)
    card = _card_in_hand_a(table)

    outcome = run_op(table, SEAT_B, ShowTo(piece_id=card, seat_ids=(SEAT_B,)))

    assert outcome == Reject("You can only show a piece whose face you can see.")
    assert _face(table, SEAT_B, card) is None


def test_a_card_still_in_the_deck_cannot_be_shown_by_anyone() -> None:
    table = build_sample_table(deck_size=1)

    for actor in (FACILITATOR, SEAT_A, SEAT_B):
        outcome = run_op(table, actor, ShowTo(piece_id="card-0"))
        assert isinstance(outcome, Reject)


def test_being_shown_a_card_does_not_let_you_show_it_on() -> None:
    table = build_sample_table(deck_size=1)
    card = _card_in_hand_a(table)
    run_op(table, SEAT_A, ShowTo(piece_id=card, seat_ids=(SEAT_B,)))

    outcome = run_op(table, SEAT_B, ShowTo(piece_id=card, seat_ids=(FACILITATOR,)))

    assert isinstance(outcome, Reject)
    assert _face(table, FACILITATOR, card) is None


def test_a_reveal_records_who_is_showing_and_to_whom() -> None:
    table = build_sample_table(deck_size=1)
    card = _card_in_hand_a(table)

    outcome = run_op(table, SEAT_A, ShowTo(piece_id=card, seat_ids=(SEAT_B,)))

    assert isinstance(outcome, Ok)
    piece_patch = next(patch for patch in outcome.patches if patch.kind == "piece")
    assert piece_patch.fields["revealed_by"] == SEAT_A
    assert piece_patch.fields["revealed_to"] == [SEAT_B]
    # That a reveal happened, and to whom, is public; the face is not.
    facilitator_view = next(p for p in project(table, FACILITATOR).pieces)
    assert facilitator_view.revealed_to == (SEAT_B,)
    assert facilitator_view.revealed_by == SEAT_A
    assert facilitator_view.component_id is None


def test_only_the_person_showing_or_the_facilitator_may_put_a_card_away() -> None:
    table = build_sample_table(deck_size=1)
    card = _card_in_hand_a(table)
    run_op(table, SEAT_A, ShowTo(piece_id=card))

    assert isinstance(run_op(table, SEAT_B, EndShow(piece_id=card)), Reject)
    assert isinstance(run_op(table, FACILITATOR, EndShow(piece_id=card)), Ok)
    assert _face(table, SEAT_B, card) is None


def test_putting_a_card_away_is_announced() -> None:
    table = build_sample_table(deck_size=1)
    card = _card_in_hand_a(table)
    run_op(table, SEAT_A, ShowTo(piece_id=card))

    outcome = run_op(table, SEAT_A, EndShow(piece_id=card))

    assert isinstance(outcome, Ok)
    events = [patch.fields for patch in outcome.patches if patch.op == "event"]
    assert events == [{"type": "show_end", "piece_id": card, "by_seat": SEAT_A}]


def test_a_card_that_is_not_being_shown_cannot_be_put_away() -> None:
    table = build_sample_table(deck_size=1)
    card = _card_in_hand_a(table)

    assert run_op(table, SEAT_A, EndShow(piece_id=card)) == Reject(
        "That piece is not being shown."
    )


def test_someone_else_cannot_take_over_a_reveal_in_progress() -> None:
    table = build_sample_table(deck_size=1)
    card = "card-0"
    table.pieces[card].zone_id = PUBLIC_TABLE
    table.pieces[card].face_up = True
    run_op(table, SEAT_A, ShowTo(piece_id=card, seat_ids=(SEAT_B,)))

    outcome = run_op(table, FACILITATOR, ShowTo(piece_id=card))

    assert outcome == Reject("Someone else is already showing that piece.")


def test_who_is_showing_survives_a_snapshot_round_trip() -> None:
    table = build_sample_table(deck_size=1)
    card = _card_in_hand_a(table)
    run_op(table, SEAT_A, ShowTo(piece_id=card, seat_ids=(SEAT_B,)))

    assert from_snapshot(to_snapshot(table)) == table


def test_moving_a_shown_card_ends_the_reveal() -> None:
    table = build_sample_table(deck_size=1)
    card = _card_in_hand_a(table)
    run_op(table, SEAT_A, ShowTo(piece_id=card, seat_ids=(SEAT_B,)))

    run_op(table, SEAT_A, MoveToZone(piece_id=card, zone_id=HAND_B))
    run_op(table, SEAT_B, MoveToZone(piece_id=card, zone_id=HAND_A))

    piece = table.pieces[card]
    assert piece.revealed_to == frozenset()
    assert piece.revealed_by is None


# -- dropping into a zone -----------------------------------------------------------


def test_a_drop_position_is_honoured_in_a_free_layout_zone() -> None:
    table = build_sample_table(deck_size=1)

    run_op(
        table,
        SEAT_A,
        MoveToZone(piece_id="card-0", zone_id=PUBLIC_TABLE, x=321, y=456),
    )

    assert (table.pieces["card-0"].x, table.pieces["card-0"].y) == (321, 456)


def test_a_laid_out_zone_places_a_dropped_piece_itself() -> None:
    table = build_sample_table(deck_size=1)

    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=DISCARD, x=999, y=999))

    # The discard pile is a stack: the piece joins it at its centre.
    assert (table.pieces["card-0"].x, table.pieces["card-0"].y) == (170, 70)


# -- stacking --------------------------------------------------------------------------


def test_stacking_puts_a_piece_on_top_of_another_wherever_it_is() -> None:
    table = build_sample_table(deck_size=3)
    for piece_id, x in (("card-0", 100.0), ("card-1", 300.0)):
        run_op(table, FACILITATOR, MoveToZone(piece_id=piece_id, zone_id=PUBLIC_TABLE))
        run_op(table, FACILITATOR, Move(piece_id=piece_id, x=x, y=300))
    table.pieces["card-1"].rotation = 12

    outcome = run_op(table, SEAT_A, StackOnto(piece_id="card-2", onto_id="card-0"))

    assert isinstance(outcome, Ok)
    stacked = table.pieces["card-2"]
    assert stacked.zone_id == PUBLIC_TABLE
    assert (stacked.x, stacked.y, stacked.rotation) == (100, 300, 0)
    others = [p for p in table.pieces_in_zone(PUBLIC_TABLE) if p.id != "card-2"]
    assert stacked.z > max(p.z for p in others)


def test_a_piece_cannot_be_stacked_on_itself() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(table, SEAT_A, StackOnto(piece_id="card-0", onto_id="card-0"))

    assert outcome == Reject("A piece cannot be stacked on itself.")


def test_stacking_respects_whoever_is_holding_the_piece() -> None:
    table = build_sample_table(deck_size=2)
    table.pieces["card-1"].held_by = SEAT_B

    outcome = run_op(table, SEAT_A, StackOnto(piece_id="card-1", onto_id="card-0"))

    assert outcome == Reject("Someone else is already holding that piece.")


def test_unstacking_is_an_ordinary_move_off_the_top() -> None:
    table = build_sample_table(deck_size=2)
    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=PUBLIC_TABLE))
    run_op(table, SEAT_A, StackOnto(piece_id="card-1", onto_id="card-0"))

    run_op(table, SEAT_A, Move(piece_id="card-1", x=600, y=500))

    assert (table.pieces["card-0"].x, table.pieces["card-0"].y) != (600, 500)
    assert table.pieces["card-1"].zone_id == PUBLIC_TABLE


# -- ink -----------------------------------------------------------------------


def _draw_strokes(table: Table) -> None:
    for seat, stroke_id in ((SEAT_A, "ink-a"), (SEAT_B, "ink-b"), (SEAT_A, "ink-a2")):
        run_op(
            table,
            seat,
            InkBegin(stroke_id=stroke_id, colour="#000", width=4, x=0, y=0),
        )


def test_clearing_your_own_ink_leaves_everyone_elses() -> None:
    table = build_sample_table(deck_size=0)
    _draw_strokes(table)

    outcome = run_op(table, SEAT_A, ClearInk())

    assert isinstance(outcome, Ok)
    assert set(table.strokes) == {"ink-b"}
    assert {patch.entity_id for patch in outcome.patches} == {"ink-a", "ink-a2"}


def test_only_the_facilitator_may_clear_everyones_ink() -> None:
    table = build_sample_table(deck_size=0)
    _draw_strokes(table)

    refused = run_op(table, SEAT_A, ClearInk(everyone=True))
    cleared = run_op(table, FACILITATOR, ClearInk(everyone=True))

    assert refused == Reject("Only the facilitator may clear everyone's ink.")
    assert isinstance(cleared, Ok)
    assert table.strokes == {}


# -- removing pieces -----------------------------------------------------------


def test_only_the_facilitator_may_remove_a_piece() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(table, SEAT_A, Despawn(piece_ids=("card-0",)))

    assert outcome == Reject("Only the facilitator may remove a piece from the table.")
    assert "card-0" in table.pieces
    assert DECK in table.zones
