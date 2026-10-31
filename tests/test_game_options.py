"""Options, filtered decks and cards nobody may show, in the generic engine."""

from __future__ import annotations

import pytest
from _games_support import FIXTURE_CONTENT, FIXTURE_GAMES, seated

from sandbox.games.engine import build_activity_start, build_table, scope_of
from sandbox.games.loader import Game, GameDefinitionError, load_game
from sandbox.model import (
    OpenActivity,
    ShowTo,
    Table,
    TableRng,
    Transaction,
    run_op,
)
from sandbox.web.live import chosen_options


def _game() -> Game:
    return load_game(FIXTURE_GAMES / "choosy", FIXTURE_CONTENT)


def _secrets(table: Table) -> list[str]:
    return sorted(
        p.component_id
        for p in table.pieces.values()
        if p.component_id.startswith("secrets:")
    )


def test_a_room_game_takes_each_options_first_choice() -> None:
    table = seated(_game(), 1)
    assert _secrets(table) == ["secrets:n1", "secrets:n2"]


def test_options_choose_which_rows_are_spawned() -> None:
    game = _game()
    table = Table(rng=TableRng(seed=0))
    seat, tx = build_table(game, table, participant_id="p", options={"side": "south"})
    run_op(table, seat, tx)
    assert _secrets(table) == ["secrets:s1"]


def test_an_activity_remembers_its_options() -> None:
    game = _game()
    table = seated_open_room()
    opened = OpenActivity("choosy", "Choosy", 1, 4, options=(("side", "south"),))
    run_op(table, "seat-1", opened)
    activity = next(iter(table.activities.values()))
    assert activity.options == {"side": "south"}
    assert scope_of(table, activity.id).options == {"side": "south"}
    built = build_activity_start(game, table, "seat-1", activity.id)
    assert isinstance(built, Transaction)
    run_op(table, "seat-1", built)
    assert _secrets(table) == ["secrets:s1"]


def seated_open_room() -> Table:
    table = Table(rng=TableRng(seed=1))
    seat, tx = build_table(None, table, participant_id="p-1")
    run_op(table, seat, tx)
    return table


def test_a_card_marked_unrevealable_cannot_be_shown() -> None:
    game = _game()
    table = seated(game, 1)
    secret = next(p for p in table.pieces.values() if p.component_id == "secrets:n1")
    secret.zone_id = "table"
    secret.face_up = True
    reason = ShowTo(piece_id=secret.id).validate(table, "seat-1")
    assert reason == "This card is never shown to anyone."
    plain = next(p for p in table.pieces.values() if p.component_id == "plain:x")
    assert ShowTo(piece_id=plain.id).validate(table, "seat-1") is None


def test_the_flag_travels_with_the_card_through_a_shuffle() -> None:
    table = seated(_game(), 1)
    assert all(
        p.props.get("revealable") is False
        for p in table.pieces.values()
        if p.component_id.startswith("secrets:")
    )


def test_an_unknown_option_or_choice_is_refused() -> None:
    game = _game()
    assert chosen_options(game, None) == {"side": "north"}
    assert chosen_options(game, {"side": "south"}) == {"side": "south"}
    assert isinstance(chosen_options(game, {"side": "west"}), str)
    assert isinstance(chosen_options(game, {"weather": "rain"}), str)


def test_a_filter_on_a_missing_column_does_not_load(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import shutil

    shutil.copytree(FIXTURE_GAMES / "choosy", tmp_path / "choosy")
    path = tmp_path / "choosy" / "game.yaml"
    path.write_text(path.read_text().replace("where: {side", "where: {nope"))
    with pytest.raises(GameDefinitionError, match="nope"):
        load_game(tmp_path / "choosy", FIXTURE_CONTENT)
