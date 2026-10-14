"""Exercise registry.

Two registries live here. ``EXERCISES`` is the public catalog, read from
``content/site/exercise*.csv``: add a row and the exercise appears
throughout the site without any template changes. ``GAMES`` is every game
definition under this package (a directory with a ``game.yaml``), keyed by
slug: what a room for that slug actually puts on its table. An exercise in
the catalog without a definition yet gets a table with seats and nothing
else.
"""

from sandbox.games.democracy import DEMOCRACY_SIMULATION
from sandbox.games.loader import Game, load_games
from sandbox.games.models import Exercise
from sandbox.games.value_cards import VALUE_CARDS_TRADING

EXERCISES: tuple[Exercise, ...] = (
    VALUE_CARDS_TRADING,
    DEMOCRACY_SIMULATION,
)

EXERCISES_BY_SLUG: dict[str, Exercise] = {
    exercise.slug: exercise for exercise in EXERCISES
}

GAMES: dict[str, Game] = load_games()


def playable_slugs() -> frozenset[str]:
    """Every slug a room may be started for: listed exercises and games."""
    return frozenset(EXERCISES_BY_SLUG) | frozenset(GAMES)


__all__ = [
    "EXERCISES",
    "EXERCISES_BY_SLUG",
    "Exercise",
    "GAMES",
    "Game",
    "playable_slugs",
]
