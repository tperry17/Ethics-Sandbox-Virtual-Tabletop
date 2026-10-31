"""Loading game definitions: the schema, the cross-checks, and validate-games."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from _games_support import FIXTURE_CONTENT, FIXTURE_GAMES, hooked, pairs
from pydantic import ValidationError

from sandbox.cli import main
from sandbox.games.definition import GameDefinition
from sandbox.games.loader import GameDefinitionError, card_component_id, load_game
from sandbox.games.validation import validate_games

PAIRS_DIR = FIXTURE_GAMES / "pairs"


def _pairs_raw() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(
        (PAIRS_DIR / "game.yaml").read_text(encoding="utf-8")
    )
    return raw


def _game_dir(tmp_path: Path, raw: dict[str, Any], rules: str | None = None) -> Path:
    directory = tmp_path / "custom"
    directory.mkdir()
    (directory / "game.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    if rules is not None:
        (directory / "rules.py").write_text(rules, encoding="utf-8")
    return directory


# -- the reference game -----------------------------------------------------------


def test_pairs_loads_with_its_deck_prompts_and_python_macro() -> None:
    game = pairs()

    assert game.slug == "pairs"
    assert not game.definition.meta.listed
    assert len(game.decks["cards"]) == 8
    assert [prompt.id for prompt in game.prompts] == [
        "kept-a-pair",
        "what-would-change",
    ]
    assert set(game.macro_functions) == {"call_pairs"}
    assert game.per_seat_zones == frozenset({"hand"})


def test_a_cards_component_id_comes_from_its_key_column() -> None:
    card = pairs().decks["cards"][0]

    assert card.component_id == card_component_id("cards", "Ace of hearts")
    assert card.component_id == "cards:ace-of-hearts"
    assert card.face.title == "Ace of hearts"
    assert card.fields["text"] == "Hearts"


def test_every_component_has_a_face() -> None:
    faces = pairs().faces()

    assert len(faces) == 8
    assert all(face.title for face in faces.values())


def test_a_hook_game_registers_every_moment() -> None:
    game = hooked()

    assert set(game.hooks) == {"after_setup", "seat_change", "before_macro"}
    assert set(game.macro_functions) == {"marker_each", "always_refuse"}


# -- the schema -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda raw: raw.update(
                macros=[m for m in raw["macros"] if m["id"] != "clear_ink"]
            ),
            "every exercise needs these macros as well",
        ),
        (
            lambda raw: raw["zones"][3].update(per_seat=False),
            "is private_to_owner but not per_seat",
        ),
        (
            lambda raw: raw["zones"].append(dict(raw["zones"][0])),
            "zone ids used more than once",
        ),
        (
            lambda raw: raw["macros"][1].update(python="call_pairs"),
            "exactly one of 'steps' or 'python'",
        ),
        (
            lambda raw: raw["meta"]["players"].update(min=3),
            "players.min is larger than players.max",
        ),
        (lambda raw: raw["meta"].update(colour="red"), "Extra inputs"),
        (
            lambda raw: raw["setup"].append({"op": "teleport", "zone": "deck"}),
            "does not match any of the expected tags",
        ),
    ],
)
def test_the_schema_refuses_a_broken_definition(change: Any, message: str) -> None:
    raw = _pairs_raw()
    change(raw)

    with pytest.raises(ValidationError, match=message):
        GameDefinition.model_validate(raw)


def test_a_die_needs_faces() -> None:
    raw = _pairs_raw()
    raw["components"]["pieces"] = [{"id": "d6", "kind": "die"}]

    with pytest.raises(ValidationError, match="needs a non-empty list of faces"):
        GameDefinition.model_validate(raw)


# -- the cross-checks loading does ------------------------------------------------


@pytest.mark.parametrize(
    ("step", "message"),
    [
        ({"op": "shuffle", "zone": "attic"}, "names a zone 'attic'"),
        (
            {"op": "deal", "from": "hand", "to": "doors"},
            "needs one zone, but 'hand' is a zone every seat has",
        ),
        ({"op": "spawn_deck", "deck": "tarot", "zone": "deck"}, "unknown deck"),
        ({"op": "spawn", "component": "doors", "zone": "deck"}, "decks use spawn_deck"),
        ({"op": "setup"}, "cannot run 'setup' inside setup"),
    ],
)
def test_loading_refuses_a_step_that_names_something_undefined(
    tmp_path: Path, step: dict[str, Any], message: str
) -> None:
    raw = _pairs_raw()
    raw["setup"].append(step)
    directory = _game_dir(
        tmp_path, raw, (PAIRS_DIR / "rules.py").read_text(encoding="utf-8")
    )

    with pytest.raises(GameDefinitionError, match=message):
        load_game(directory, FIXTURE_CONTENT)


def test_loading_refuses_a_python_macro_with_no_function(tmp_path: Path) -> None:
    directory = _game_dir(tmp_path, _pairs_raw())

    with pytest.raises(GameDefinitionError, match="registers no @macro"):
        load_game(directory, FIXTURE_CONTENT)


def test_loading_refuses_a_function_no_macro_uses(tmp_path: Path) -> None:
    rules = (PAIRS_DIR / "rules.py").read_text(encoding="utf-8")
    rules += '\n\n@macro("spare")\ndef spare(table, context):\n    return []\n'
    directory = _game_dir(tmp_path, _pairs_raw(), rules)

    with pytest.raises(GameDefinitionError, match="no macro in game.yaml"):
        load_game(directory, FIXTURE_CONTENT)


@pytest.fixture
def content_root(tmp_path: Path) -> Path:
    """A content folder of the test's own, holding a copy of Pairs' text."""
    root = tmp_path / "content"
    shutil.copytree(
        FIXTURE_CONTENT / "exercises" / "pairs", root / "exercises" / "pairs"
    )
    return root


def _rewrite_deck(content_root: Path, text: str) -> None:
    deck = content_root / "exercises" / "pairs" / "cards.csv"
    deck.write_text(text, encoding="utf-8")


def test_loading_refuses_two_cards_with_the_same_key(content_root: Path) -> None:
    _rewrite_deck(content_root, "name,text,image\nSame,a,\nSame,b,\n")

    with pytest.raises(GameDefinitionError, match="lines 2 and 3 both make"):
        load_game(PAIRS_DIR, content_root)


def test_loading_refuses_an_image_that_is_not_there(content_root: Path) -> None:
    _rewrite_deck(content_root, "name,text,image\nOne,a,missing.png\n")

    with pytest.raises(GameDefinitionError, match="not in its images/ folder"):
        load_game(PAIRS_DIR, content_root)


def test_loading_refuses_a_column_the_deck_does_not_have(content_root: Path) -> None:
    _rewrite_deck(content_root, "title,text,image\nOne,a,\n")

    with pytest.raises(GameDefinitionError, match="column 'name'"):
        load_game(PAIRS_DIR, content_root)


def test_an_image_card_is_served_from_the_content_route(content_root: Path) -> None:
    images = content_root / "exercises" / "pairs" / "images"
    (images / "door.png").write_bytes(b"\x89PNG")
    _rewrite_deck(content_root, "name,text,image\nOne,a,door.png\n")

    card = load_game(PAIRS_DIR, content_root).decks["cards"][0]

    assert card.face.image == "/content/exercises/pairs/images/door.png"


# -- validate-games ---------------------------------------------------------------


def test_every_game_in_the_repo_is_valid() -> None:
    assert validate_games().errors == []


def test_every_fixture_game_is_valid() -> None:
    report = validate_games(FIXTURE_GAMES, FIXTURE_CONTENT, catalog_notes=False)

    assert report.errors == []
    assert sorted(report.checked) == ["choosy", "hooked", "pairs"]


def test_pairs_is_not_part_of_the_product() -> None:
    from sandbox.games.loader import load_games

    assert "pairs" not in load_games()


def test_validate_games_notes_catalog_exercises_without_a_definition() -> None:
    report = validate_games()

    assert any("democracy-simulation" in note for note in report.notes)


def test_validate_games_reports_a_broken_definition(tmp_path: Path) -> None:
    shutil.copytree(FIXTURE_GAMES / "hooked", tmp_path / "hooked")
    raw = _pairs_raw()
    raw["setup"].append({"op": "shuffle", "zone": "attic"})
    _game_dir(tmp_path, raw)

    report = validate_games(tmp_path, FIXTURE_CONTENT, catalog_notes=False)

    assert not report.ok
    assert any("attic" in error for error in report.errors)
    assert "hooked" in report.checked


def test_the_cli_exits_zero_when_every_game_is_valid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["validate-games"]) == 0
    assert "checked pairs" in capsys.readouterr().out


# -- what the buttons say ----------------------------------------------------------


def _rewrite_buttons(content_root: Path, text: str) -> None:
    buttons = content_root / "exercises" / "pairs" / "buttons.csv"
    buttons.write_text(text, encoding="utf-8")


def test_button_wording_comes_from_the_games_csv() -> None:
    button = pairs().buttons["reset"]

    assert button.label == "Reset"
    assert button.confirm is not None and button.confirm.startswith("This removes")
    assert pairs().buttons["shuffle"].hint is None


def test_a_button_with_no_announcement_gets_the_plain_one() -> None:
    assert hooked().buttons["deal"].announce == "{name} pressed “{label}”."


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda rows: rows[:-1], r"has no row for \['clear_ink'\]"),
        (lambda rows: [*rows, "spare,Spare,,,"], "which game.yaml does not define"),
        (lambda rows: [*rows[:-1], "clear_ink,,,,"], "has no label"),
        (
            lambda rows: [*rows[:-1], "clear_ink,Clear ink,,,{who} cleared it"],
            r"announces with \['who'\]",
        ),
        (lambda rows: [*rows, rows[-1]], "two rows for 'clear_ink'"),
    ],
)
def test_loading_refuses_a_buttons_csv_that_does_not_match(
    content_root: Path, change: Any, message: str
) -> None:
    path = content_root / "exercises" / "pairs" / "buttons.csv"
    header, *rows = path.read_text(encoding="utf-8").splitlines()
    _rewrite_buttons(content_root, "\n".join([header, *change(rows)]) + "\n")

    with pytest.raises(GameDefinitionError, match=message):
        load_game(PAIRS_DIR, content_root)
