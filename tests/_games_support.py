"""Tables built from game definitions, for the game tests.

Not a test module itself.
"""

from __future__ import annotations

from pathlib import Path

from sandbox.games import GAMES
from sandbox.games.engine import build_macro, build_seat, build_table
from sandbox.games.loader import Game, load_game
from sandbox.model import Ok, OpOutcome, Reject, Table, TableRng, run_op

FIXTURE_GAMES = Path(__file__).resolve().parent / "games"
FIXTURE_CONTENT = FIXTURE_GAMES / "content"


def two_doors() -> Game:
    return GAMES["two-doors"]


def hooked() -> Game:
    return load_game(FIXTURE_GAMES / "hooked", FIXTURE_CONTENT)


def seated(game: Game, people: int, *, seed: int = 0) -> Table:
    """``game``'s table, set up, with ``people`` seats taken."""
    table = Table(rng=TableRng(seed=seed))
    seat_id, transaction = build_table(game, table, participant_id="p-1")
    assert isinstance(run_op(table, seat_id, transaction), Ok)
    for person in range(2, people + 1):
        seat_id, transaction = build_seat(game, table, participant_id=f"p-{person}")
        assert isinstance(run_op(table, seat_id, transaction), Ok)
    return table


def press(game: Game, table: Table, macro_id: str, seat: str = "seat-1") -> OpOutcome:
    """Press ``macro_id`` as ``seat``: the refusal, or the applied outcome."""
    built = build_macro(game, table, seat, macro_id)
    if isinstance(built, Reject):
        return built
    return run_op(table, seat, built)
