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
from sandbox.model.entities import Activity, Rect, Table, Zone
from sandbox.model.ops import Deal, ShowTo, run_op
from sandbox.model.results import Ok
from sandbox.model.types import Layout, Visibility, ZoneKind


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


def test_removing_is_offered_to_the_facilitator_only_and_locking_to_anyone() -> None:
    table = build_sample_table(deck_size=1)

    assert {"lock", "delete"} <= set(_keys(table, "card-0", FACILITATOR))
    assert "lock" in _keys(table, "card-0", SEAT_A)
    assert "delete" not in _keys(table, "card-0", SEAT_A)


def _seated(table: Table) -> Table:
    for seat in table.seats.values():
        seat.participant_id = f"person-{seat.id}"
    return table


def test_a_card_in_a_deck_offers_a_shuffle_and_a_deal_to_every_player() -> None:
    table = _seated(build_sample_table(deck_size=6))

    entries = {e.key: e for e in piece_actions(table, "card-0", SEAT_A)}

    assert "shuffle" in entries
    assert {"deal:1", "deal:3"} <= set(entries)
    assert "deal:5" not in entries  # six cards do not go round two players five times
    deal = entries["deal:3"].operation
    assert isinstance(deal, Deal)
    # Every player's hand, in seat order; the facilitator's tray is not a hand.
    assert deal.to_zones == (HAND_A, HAND_B)
    assert deal.face_up is True
    assert isinstance(run_op(table, SEAT_A, deal), Ok)
    assert len(table.pieces_in_zone(HAND_A)) == 3
    assert len(table.pieces_in_zone(HAND_B)) == 3


def test_a_deal_skips_an_empty_seat_and_the_facilitator() -> None:
    table = _seated(build_sample_table(deck_size=6))
    table.seats[SEAT_B].participant_id = None
    table.zones["hand-f"] = Zone(
        id="hand-f",
        kind=ZoneKind.HAND,
        label="Facilitator's hand",
        geometry=Rect(0, 0, 10, 10),
        visibility=Visibility.PRIVATE_TO_OWNER,
        layout=Layout.FAN,
        owner_seat=FACILITATOR,
    )

    deal = {e.key: e for e in piece_actions(table, "card-0", SEAT_A)}["deal:1"]

    assert isinstance(deal.operation, Deal)
    assert deal.operation.to_zones == (HAND_A,)


def test_a_deck_in_an_activity_deals_to_that_activitys_hands_only() -> None:
    table = _seated(build_sample_table(deck_size=6))
    table.activities["activity-1"] = Activity(
        id="activity-1",
        kind="pairs",
        title="Pairs",
        min_players=1,
        max_players=2,
        seats=(SEAT_B,),
        status="running",
        zones=(DECK, HAND_B),
    )

    deal = {e.key: e for e in piece_actions(table, "card-0", SEAT_B)}["deal:1"]

    assert isinstance(deal.operation, Deal)
    assert deal.operation.to_zones == (HAND_B,)


def test_a_card_outside_a_deck_offers_neither_shuffle_nor_deal() -> None:
    table = _seated(build_sample_table(deck_size=1))
    table.pieces["card-0"].zone_id = PUBLIC_TABLE
    table.pieces["card-0"].face_up = True

    keys = _keys(table, "card-0", SEAT_A)

    assert "shuffle" not in keys
    assert not any(key.startswith("deal:") for key in keys)


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
