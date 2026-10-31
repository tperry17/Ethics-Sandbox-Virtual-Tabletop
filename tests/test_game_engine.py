"""Building tables, seats and macros from game definitions."""

from __future__ import annotations

import copy
import dataclasses

from _games_support import hooked, press, seated, two_doors

from sandbox.db.snapshot import to_snapshot
from sandbox.games import Game
from sandbox.games.definition import GameDefinition
from sandbox.games.engine import (
    announcement,
    build_macro,
    build_seat,
    build_table,
    seat_order,
)
from sandbox.model import (
    Ok,
    Rect,
    Reject,
    Table,
    TableRng,
    Transaction,
    Visibility,
    project,
    run_op,
)
from sandbox.model.types import PieceKind


def _component_ids_seen(table: Table, seat: str | None) -> set[str]:
    view = project(table, seat)
    return {piece.component_id for piece in view.pieces if piece.component_id}


# -- building the table -----------------------------------------------------------


def test_a_new_table_has_shared_zones_then_the_facilitators_own() -> None:
    table = seated(two_doors(), 1)

    assert list(table.zones) == ["table", "deck", "doors", "hand-seat-1"]
    assert table.seats["seat-1"].is_facilitator
    assert table.seats["seat-1"].label == "First seat"
    assert table.zones["hand-seat-1"].owner_seat == "seat-1"
    assert table.zones["hand-seat-1"].label == "Hand · First seat"


def test_setup_lays_out_the_whole_deck_face_down_and_unreadable() -> None:
    table = seated(two_doors(), 2)

    deck = table.pieces_in_zone("deck")
    assert len(deck) == 6
    assert table.zones["deck"].visibility is Visibility.HIDDEN
    for seat in (None, "seat-1", "seat-2"):
        assert _component_ids_seen(table, seat) == set()


def test_a_spawned_cards_id_says_nothing_about_which_card_it_is() -> None:
    table = seated(two_doors(), 1)

    for piece in table.pieces.values():
        assert piece.component_id.split(":")[1] not in piece.id


def test_each_seat_gets_its_own_zone_moved_by_the_step() -> None:
    table = seated(two_doors(), 2)

    first = table.zones["hand-seat-1"].geometry
    second = table.zones["hand-seat-2"].geometry
    assert isinstance(first, Rect) and isinstance(second, Rect)
    assert (second.x, second.y) == (first.x, first.y - 680)
    assert table.seats["seat-2"].label == "Second seat"


def test_seats_past_the_named_ones_are_numbered() -> None:
    table = seated(hooked(), 3)

    assert [table.seats[seat].label for seat in seat_order(table)] == [
        "Seat 1",
        "Seat 2",
        "Seat 3",
    ]


def test_seat_order_counts_rather_than_sorting_text() -> None:
    table = Table()
    for _ in range(11):
        seat_id, transaction = build_seat(None, table, participant_id=None)
        assert isinstance(run_op(table, seat_id, transaction), Ok)

    assert seat_order(table)[8:] == ("seat-9", "seat-10", "seat-11")


def test_a_game_without_a_definition_gets_seats_and_nothing_else() -> None:
    table = Table()
    seat_id, transaction = build_table(
        None, table, participant_id="p-1", as_facilitator=True
    )

    assert isinstance(run_op(table, seat_id, transaction), Ok)
    assert list(table.seats) == ["seat-1"]
    assert table.zones == {}
    assert table.pieces == {}


def test_the_same_seed_builds_the_same_table() -> None:
    first = seated(two_doors(), 2, seed=9)
    second = seated(two_doors(), 2, seed=9)

    def faces(table: Table) -> list[str]:
        return [piece.component_id for piece in table.pieces_in_zone("deck")]

    assert faces(first) == faces(second)


# -- macros -----------------------------------------------------------------------


def test_dealing_puts_one_readable_card_in_each_hand() -> None:
    game = two_doors()
    table = seated(game, 2)

    assert isinstance(press(game, table, "deal"), Ok)

    mine = table.pieces_in_zone("hand-seat-1")
    theirs = table.pieces_in_zone("hand-seat-2")
    assert len(mine) == len(theirs) == 1
    assert mine[0].face_up and theirs[0].face_up
    assert _component_ids_seen(table, "seat-1") == {mine[0].component_id}
    assert _component_ids_seen(table, "seat-2") == {theirs[0].component_id}
    assert _component_ids_seen(table, None) == set()


def test_reveal_lays_each_seats_card_on_the_doors_in_seat_order() -> None:
    game = two_doors()
    table = seated(game, 2)
    press(game, table, "deal")
    first = table.pieces_in_zone("hand-seat-1")[0].id
    second = table.pieces_in_zone("hand-seat-2")[0].id

    assert isinstance(press(game, table, "reveal"), Ok)

    assert [piece.id for piece in table.pieces_in_zone("doors")] == [first, second]
    assert len(_component_ids_seen(table, None)) == 2


def test_reveal_refuses_before_the_deal_with_its_own_reason() -> None:
    game = two_doors()
    table = seated(game, 2)

    outcome = press(game, table, "reveal")

    assert outcome == Reject("First seat has no card to reveal. Deal first.")


def test_reveal_refuses_twice() -> None:
    game = two_doors()
    table = seated(game, 2)
    press(game, table, "deal")
    press(game, table, "reveal")
    press(game, table, "deal")

    outcome = press(game, table, "reveal")

    assert outcome == Reject("The doors already hold cards. Collect them first.")


def test_a_facilitators_macro_is_refused_to_anyone_else() -> None:
    game = two_doors()
    table = seated(game, 2)

    outcome = press(game, table, "reset", seat="seat-2")

    assert outcome == Reject("Only the facilitator can use “Reset”.")


def test_an_unknown_macro_is_refused() -> None:
    outcome = press(two_doors(), seated(two_doors(), 1), "nothing")

    assert isinstance(outcome, Reject)


def test_a_macro_that_fails_part_way_changes_nothing_at_all() -> None:
    game = two_doors()
    table = seated(game, 2)
    for _ in range(2):
        press(game, table, "deal")
    press(game, table, "deal")
    before = to_snapshot(table)

    # Six cards, two seats: the fourth deal has nothing left to give.
    outcome = press(game, table, "deal")

    assert outcome == Reject("Only 0 pieces remain in Deck, but dealing needs 2.")
    assert to_snapshot(table) == before


def test_collect_brings_every_card_back_and_the_shuffle_hides_which_is_which() -> None:
    game = two_doors()
    table = seated(game, 2, seed=4)
    press(game, table, "deal")
    press(game, table, "reveal")
    shown = {piece.id: piece.component_id for piece in table.pieces_in_zone("doors")}

    assert isinstance(press(game, table, "collect"), Ok)

    assert len(table.pieces_in_zone("deck")) == 6
    assert all(not piece.face_up for piece in table.pieces.values())
    # Not every shown card can still be found under the same id.
    assert any(table.pieces[pid].component_id != cid for pid, cid in shown.items())


def test_set_up_starts_the_table_again() -> None:
    game = two_doors()
    table = seated(game, 2)
    press(game, table, "deal")

    assert isinstance(press(game, table, "setup"), Ok)

    assert len(table.pieces_in_zone("deck")) == 6
    assert table.pieces_in_zone("hand-seat-1") == []


def test_reset_clears_every_piece() -> None:
    game = two_doors()
    table = seated(game, 2)

    assert isinstance(press(game, table, "reset"), Ok)

    assert table.pieces == {}
    assert list(table.zones) == ["table", "deck", "doors", "hand-seat-1", "hand-seat-2"]


def test_every_macro_is_one_transaction_named_for_it() -> None:
    game = two_doors()
    table = seated(game, 2)

    built = build_macro(game, table, "seat-1", "deal")

    assert isinstance(built, Transaction)
    assert built.name == "macro:deal"
    assert built.label == "Deal one each"


def test_building_a_macro_does_not_touch_the_table() -> None:
    game = two_doors()
    table = seated(game, 2)
    before = to_snapshot(table)

    build_macro(game, table, "seat-1", "deal")

    assert to_snapshot(table) == before


def test_the_announcement_names_who_pressed_it() -> None:
    assert (
        announcement(two_doors(), "deal", "Ana") == "Ana dealt one card to each seat."
    )


def test_a_table_replayed_from_its_transactions_is_the_same_table() -> None:
    game = two_doors()
    original = Table(rng=TableRng(seed=11))
    log: list[tuple[str, Transaction]] = []

    seat_id, transaction = build_table(
        game, original, participant_id="p-1", as_facilitator=True
    )
    log.append((seat_id, transaction))
    run_op(original, seat_id, transaction)
    seat_id, transaction = build_seat(game, original, participant_id="p-2")
    log.append((seat_id, transaction))
    run_op(original, seat_id, transaction)
    for macro_id in ("deal", "reveal", "collect", "deal", "shuffle"):
        built = build_macro(game, original, "seat-1", macro_id)
        assert isinstance(built, Transaction)
        log.append(("seat-1", built))
        run_op(original, "seat-1", built)

    replayed = Table(rng=TableRng(seed=11))
    for actor, transaction in log:
        assert isinstance(run_op(replayed, actor, copy.deepcopy(transaction)), Ok)

    assert to_snapshot(replayed) == to_snapshot(original)


# -- hooks --------------------------------------------------------------------------


def test_after_setup_hooks_run_inside_the_setup() -> None:
    table = seated(hooked(), 1)

    die = next(p for p in table.pieces.values() if p.kind is PieceKind.DIE)
    assert die.props["value"] in die.props["faces"]  # type: ignore[operator]


def test_seat_change_hooks_run_for_every_new_seat() -> None:
    table = seated(hooked(), 3)

    for seat in ("seat-1", "seat-2", "seat-3"):
        assert table.pieces[f"welcome-{seat}"].zone_id == f"tray-{seat}"


def test_before_macro_hooks_run_before_the_macro_in_the_same_transaction() -> None:
    game = hooked()
    table = seated(game, 2)

    assert isinstance(press(game, table, "deal"), Ok)

    die = next(p for p in table.pieces.values() if p.kind is PieceKind.DIE)
    assert die.props["last_macro"] == "deal"
    assert len(table.pieces_in_zone("tray-seat-2")) == 2


def test_a_python_macro_refuses_with_its_own_sentence() -> None:
    game = hooked()
    table = seated(game, 2)
    before = to_snapshot(table)

    outcome = press(game, table, "refuse", seat="seat-2")

    assert outcome == Reject("Not today.")
    assert to_snapshot(table) == before


def test_an_anyone_macro_that_needs_the_facilitator_is_refused_by_the_model() -> None:
    game = hooked()
    table = seated(game, 2)

    outcome = press(game, table, "clear_ink", seat="seat-2")

    assert outcome == Reject("Only the facilitator may clear everyone's ink.")


def _with_deal(steps: list[dict[str, object]]) -> Game:
    """Two Doors, with its Deal button doing ``steps`` instead."""
    game = two_doors()
    raw = game.definition.model_dump(by_alias=True)
    raw["macros"] = [
        {**macro, "steps": steps} if macro["id"] == "deal" else macro
        for macro in raw["macros"]
    ]
    return dataclasses.replace(game, definition=GameDefinition.model_validate(raw))


def test_a_card_dealt_to_a_public_zone_stays_as_it_came_off_the_deck() -> None:
    game = _with_deal([{"op": "draw", "from": "deck", "to": "doors", "count": 1}])
    table = seated(game, 1)

    assert isinstance(press(game, table, "deal"), Ok)

    assert [piece.face_up for piece in table.pieces_in_zone("doors")] == [False]


def test_a_deal_that_says_face_down_keeps_a_hand_card_face_down() -> None:
    game = _with_deal(
        [{"op": "deal", "from": "deck", "to": "hand", "count": 1, "face_up": False}]
    )
    table = seated(game, 1)

    assert isinstance(press(game, table, "deal"), Ok)

    assert [piece.face_up for piece in table.pieces_in_zone("hand-seat-1")] == [False]
    assert _component_ids_seen(table, "seat-1") == set()
