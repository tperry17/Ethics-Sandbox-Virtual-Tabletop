"""The context menu: what one seat may do to one piece, decided by the model."""

from __future__ import annotations

import copy

from _model_support import (
    DECK,
    FACILITATOR,
    HAND_A,
    HAND_B,
    PUBLIC_TABLE,
    SEAT_A,
    SEAT_B,
    build_die,
    build_sample_table,
)
from hypothesis import given, settings
from hypothesis import strategies as st

from sandbox.model.actions import piece_actions
from sandbox.model.entities import Table
from sandbox.model.ops import ShowTo, run_op
from sandbox.model.results import Ok


def _keys(table: Table, piece_id: str, seat: str) -> list[str]:
    return [entry.key for entry in piece_actions(table, piece_id, seat)]


def _hand_card(table: Table) -> str:
    table.pieces["card-0"].zone_id = HAND_A
    table.pieces["card-0"].face_up = True
    return "card-0"


def test_the_owner_of_a_hand_card_may_show_it_and_look_at_it() -> None:
    table = build_sample_table(deck_size=1)
    card = _hand_card(table)

    keys = _keys(table, card, SEAT_A)

    assert "look" in keys
    assert "show_table" in keys
    assert {f"show_to:{FACILITATOR}", f"show_to:{SEAT_B}"} <= set(keys)
    assert f"show_to:{SEAT_A}" not in keys
    assert f"to_hand:{HAND_A}" not in keys


def test_someone_else_may_not_show_or_look_at_a_card_in_another_hand() -> None:
    table = build_sample_table(deck_size=1)
    card = _hand_card(table)

    keys = _keys(table, card, SEAT_B)

    assert "look" not in keys
    assert "show_table" not in keys
    assert not any(key.startswith("show_to:") for key in keys)


def test_a_card_already_visible_to_everyone_offers_no_reveal() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].zone_id = PUBLIC_TABLE
    table.pieces["card-0"].face_up = True

    keys = _keys(table, "card-0", SEAT_A)

    assert "show_table" not in keys
    assert "look" in keys


def test_a_card_being_shown_offers_to_stop_showing_it() -> None:
    table = build_sample_table(deck_size=1)
    card = _hand_card(table)
    run_op(table, SEAT_A, ShowTo(piece_id=card))

    assert "end_show" in _keys(table, card, SEAT_A)
    assert "end_show" not in _keys(table, card, SEAT_B)


def test_locking_and_removing_are_offered_to_the_facilitator_only() -> None:
    table = build_sample_table(deck_size=1)

    assert {"lock", "delete"} <= set(_keys(table, "card-0", FACILITATOR))
    assert not {"lock", "delete"} & set(_keys(table, "card-0", SEAT_A))


def test_a_die_may_be_rolled() -> None:
    table = build_sample_table(deck_size=0)
    table.pieces["die-1"] = build_die()

    assert "roll" in _keys(table, "die-1", SEAT_A)


def test_send_to_my_hand_targets_the_asking_seats_own_hand() -> None:
    table = build_sample_table(deck_size=1)

    entries = {e.key: e for e in piece_actions(table, "card-0", SEAT_B)}

    assert f"to_hand:{HAND_B}" in entries
    assert f"to_hand:{HAND_A}" not in entries
    # Someone else's hand is still a place a card can go; it is labelled
    # with whose it is.
    assert entries[f"move:{HAND_A}"].seat_id == SEAT_A


def test_a_piece_someone_else_is_holding_offers_nothing_that_would_move_it() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].held_by = SEAT_B

    keys = _keys(table, "card-0", SEAT_A)

    assert not any(key.startswith(("move:", "to_hand:")) for key in keys)
    assert "flip" not in keys


def test_an_unknown_piece_or_seat_has_an_empty_menu() -> None:
    table = build_sample_table(deck_size=1)

    assert piece_actions(table, "no-such-piece", SEAT_A) == []
    assert piece_actions(table, "card-0", "no-such-seat") == []


@given(
    piece_index=st.integers(0, 3),
    zone=st.sampled_from([DECK, PUBLIC_TABLE, HAND_A, HAND_B]),
    face_up=st.booleans(),
    seat=st.sampled_from([FACILITATOR, SEAT_A, SEAT_B]),
)
@settings(max_examples=80)
def test_every_entry_offered_is_accepted_and_asking_changes_nothing(
    piece_index: int, zone: str, face_up: bool, seat: str
) -> None:
    table = build_sample_table(deck_size=4)
    piece_id = f"card-{piece_index}"
    table.pieces[piece_id].zone_id = zone
    table.pieces[piece_id].face_up = face_up
    before = copy.deepcopy(table)

    entries = piece_actions(table, piece_id, seat)

    assert table == before
    for entry in entries:
        trial = copy.deepcopy(table)
        assert isinstance(run_op(trial, seat, entry.operation), Ok), entry.key
