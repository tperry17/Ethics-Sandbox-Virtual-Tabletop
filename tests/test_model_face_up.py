"""A card drawn off a deck, or put into a hand, lands face up."""

from _model_support import (
    DECK,
    DISCARD,
    FACILITATOR_TRAY,
    HAND_A,
    PUBLIC_TABLE,
    SEAT_A,
    SEAT_B,
    build_sample_table,
)

from sandbox.model.entities import Rect, Zone
from sandbox.model.ops import Draw, MoveToZone, StackOnto, run_op
from sandbox.model.results import Ok
from sandbox.model.types import Layout, Visibility, ZoneKind
from sandbox.model.visibility import project


def test_a_card_drawn_onto_the_table_turns_face_up() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(
        table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=PUBLIC_TABLE, x=300, y=300)
    )

    assert isinstance(outcome, Ok)
    assert table.pieces["card-0"].face_up is True
    seen = next(p for p in project(table, SEAT_B).pieces if p.id == "card-0")
    assert seen.component_id == "the-0-of-values"


def test_a_card_drawn_into_your_hand_is_face_up_for_you_alone() -> None:
    table = build_sample_table(deck_size=1)

    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=HAND_A))

    assert table.pieces["card-0"].face_up is True
    mine = next(p for p in project(table, SEAT_A).pieces if p.id == "card-0")
    theirs = next(p for p in project(table, SEAT_B).pieces if p.id == "card-0")
    assert mine.component_id == "the-0-of-values"
    assert theirs.component_id is None


def test_a_face_down_card_put_into_a_hand_turns_face_up() -> None:
    table = build_sample_table(deck_size=1)
    card = table.pieces["card-0"]
    card.zone_id, card.face_up = PUBLIC_TABLE, False

    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=HAND_A))

    assert card.face_up is True


def test_a_face_down_card_put_on_the_discard_pile_turns_face_up() -> None:
    table = build_sample_table(deck_size=1)
    card = table.pieces["card-0"]
    card.zone_id, card.face_up = PUBLIC_TABLE, False

    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=DISCARD))

    assert card.face_up is True


def test_a_card_drawn_onto_the_discard_pile_by_a_step_turns_face_up() -> None:
    table = build_sample_table(deck_size=2)

    run_op(table, SEAT_A, Draw(from_zone=DECK, to_zone=DISCARD, count=1))
    assert [p.face_up for p in table.pieces_in_zone(DISCARD)] == [True]

    # A step that says which way up still decides.
    run_op(table, SEAT_A, Draw(from_zone=DECK, to_zone=DISCARD, count=1, face_up=False))
    assert [p.face_up for p in table.pieces_in_zone(DISCARD)] == [True, False]


def test_a_face_down_card_moved_about_the_open_table_stays_face_down() -> None:
    table = build_sample_table(deck_size=1)
    card = table.pieces["card-0"]
    card.zone_id, card.face_up = PUBLIC_TABLE, False

    run_op(
        table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=PUBLIC_TABLE, x=300, y=300)
    )

    assert card.face_up is False


def test_a_card_moved_within_its_deck_or_into_another_deck_is_left_as_it_is() -> None:
    table = build_sample_table(deck_size=1)
    table.zones["deck-2"] = Zone(
        id="deck-2",
        kind=ZoneKind.DECK,
        label="Second deck",
        geometry=Rect(x=0, y=900, width=100, height=140),
        visibility=Visibility.PUBLIC,
        layout=Layout.STACK,
    )

    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=DECK))
    assert table.pieces["card-0"].face_up is False
    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id="deck-2"))
    assert table.pieces["card-0"].face_up is False


def test_a_card_drawn_into_a_zone_that_hides_faces_is_left_as_it_is() -> None:
    table = build_sample_table(deck_size=1)
    table.zones[FACILITATOR_TRAY].visibility = Visibility.HIDDEN

    run_op(
        table, "facilitator", MoveToZone(piece_id="card-0", zone_id=FACILITATOR_TRAY)
    )

    assert table.pieces["card-0"].face_up is False


def test_a_card_drawn_onto_another_piece_turns_face_up() -> None:
    table = build_sample_table(deck_size=2)
    other = table.pieces["card-1"]
    other.zone_id, other.face_up, other.x, other.y = PUBLIC_TABLE, True, 300, 300

    outcome = run_op(table, SEAT_A, StackOnto(piece_id="card-0", onto_id="card-1"))

    assert isinstance(outcome, Ok)
    assert table.pieces["card-0"].face_up is True
