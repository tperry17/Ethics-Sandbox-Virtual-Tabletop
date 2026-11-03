"""Definition for the Leadership and Knowledge in Popular Rule exercise.

Its catalog and detail-page copy lives in ``content/site/exercise*.csv``,
keyed by this slug (see ``content/README.md``). Once the game-definition
system exists, its roles come from
``content/exercises/democracy-simulation/roles.csv``.
"""

from sandbox.games.content import load_exercise

DEMOCRACY_SIMULATION = load_exercise("democracy-simulation")
