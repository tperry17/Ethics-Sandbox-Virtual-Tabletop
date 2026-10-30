"""Definition for the Value Cards Trading exercise.

Its catalog and detail-page copy lives in ``content/site/exercise*.csv``,
keyed by this slug (see ``content/README.md``). Once the game-definition
system exists, its actual deck comes from
``content/decks/value-cards/cards.csv``.
"""

from sandbox.games.content import load_exercise

VALUE_CARDS_TRADING = load_exercise("value-cards-trading")
