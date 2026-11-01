"""Exercise registry.

Two registries live here. ``EXERCISES`` is the public catalog, read from
``content/site/exercise*.csv``: add a row and the exercise appears
throughout the site without any template changes. ``GAMES`` is every game
definition under this package (a directory with a ``game.yaml``), keyed by
slug: what a room for that slug actually puts on its table. An exercise in
the catalog without a definition yet gets a table with seats and nothing
else.

``SANDBOX_EXTRA_GAMES`` names further folders of games, separated like
``PATH``, each with its own ``content/`` folder beside the games. The tests
use it to load their fixture games (``tests/games``) into a running server;
nothing in production sets it.
"""

import importlib
import os
from pathlib import Path

from sandbox.games.democracy import DEMOCRACY_SIMULATION
from sandbox.games.loader import Game, GameDefinitionError, load_games
from sandbox.games.models import Exercise
from sandbox.games.value_cards import VALUE_CARDS_TRADING

EXERCISES: tuple[Exercise, ...] = (
    VALUE_CARDS_TRADING,
    DEMOCRACY_SIMULATION,
)

EXERCISES_BY_SLUG: dict[str, Exercise] = {
    exercise.slug: exercise for exercise in EXERCISES
}

# The game of an open room: the sandbox itself, which is not an activity.
OPEN_ROOM_SLUG = "sandbox"

EXTRA_GAMES_VARIABLE = "SANDBOX_EXTRA_GAMES"


def extra_game_roots() -> list[Path]:
    """The folders ``SANDBOX_EXTRA_GAMES`` names, if any."""
    value = os.environ.get(EXTRA_GAMES_VARIABLE, "")
    return [Path(entry).resolve() for entry in value.split(os.pathsep) if entry]


def _load_all() -> dict[str, Game]:
    games = load_games()
    for root in extra_game_roots():
        for slug, game in load_games(root, root / "content").items():
            if slug in games:
                raise GameDefinitionError(
                    f"{root} has a game {slug!r}, and so does sandbox/games/."
                )
            games[slug] = game
    return games


GAMES: dict[str, Game] = _load_all()


# Each exercise's reading of the log registers itself on import.
for _module in (
    "sandbox.games.democracy_simulation.debrief",
    "sandbox.games.value_cards_trading.debrief",
):
    importlib.import_module(_module)


def playable_slugs() -> frozenset[str]:
    """Every slug a room may be started for: listed exercises and games."""
    return frozenset(EXERCISES_BY_SLUG) | frozenset(GAMES)


__all__ = [
    "EXERCISES",
    "EXTRA_GAMES_VARIABLE",
    "EXERCISES_BY_SLUG",
    "Exercise",
    "GAMES",
    "OPEN_ROOM_SLUG",
    "Game",
    "extra_game_roots",
    "playable_slugs",
]
