"""Exercise registry.

Add an imported definition to ``EXERCISES`` and it will appear throughout the
public site without any template changes.
"""

from sandbox.games.democracy import DEMOCRACY_SIMULATION
from sandbox.games.models import Exercise
from sandbox.games.value_cards import VALUE_CARDS_TRADING

EXERCISES: tuple[Exercise, ...] = (
    VALUE_CARDS_TRADING,
    DEMOCRACY_SIMULATION,
)

EXERCISES_BY_SLUG: dict[str, Exercise] = {
    exercise.slug: exercise for exercise in EXERCISES
}

__all__ = ["EXERCISES", "EXERCISES_BY_SLUG", "Exercise"]
