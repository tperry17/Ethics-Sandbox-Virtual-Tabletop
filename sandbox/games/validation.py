"""Checking every game definition, for ``uv run sandbox validate-games``.

Loading a game already checks its schema and every name it uses. This goes
one step further and plays it: for the smallest and the largest table the
definition allows, it builds the table, seats everyone, and presses every
macro, once on a freshly set-up table and once more in sequence. A macro
that refuses is fine - "deal first" is a refusal - but one that raises is a
broken definition, and so is a table that cannot be built at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sandbox.content_loading import read_rows
from sandbox.games.engine import build_macro, build_seat, build_table
from sandbox.games.loader import (
    GAMES_ROOT,
    Game,
    GameDefinitionError,
    game_directories,
    load_game,
)
from sandbox.model import Reject, Table, TableRng, run_op

EXERCISES_CSV = "site/exercises.csv"


@dataclass
class Report:
    """What a validation run found. Errors fail the run; notes do not."""

    checked: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _seated_table(game: Game, people: int, seed: int) -> Table:
    table = Table(rng=TableRng(seed=seed))
    seat_id, transaction = build_table(game, table, participant_id="check-1")
    outcome = run_op(table, seat_id, transaction)
    if isinstance(outcome, Reject):
        raise GameDefinitionError(f"its table cannot be built: {outcome.reason}")
    for person in range(2, people + 1):
        seat_id, transaction = build_seat(game, table, participant_id=f"check-{person}")
        outcome = run_op(table, seat_id, transaction)
        if isinstance(outcome, Reject):
            raise GameDefinitionError(f"seat {person} cannot sit: {outcome.reason}")
    return table


def play_through(game: Game, seed: int = 0) -> None:
    """Press every macro at both ends of the player range. Raises on a defect."""
    meta = game.definition.meta
    for people in sorted({meta.players.min, meta.players.max}):
        sequence = _seated_table(game, people, seed)
        for macro in game.definition.macros:
            fresh = _seated_table(game, people, seed)
            for table in (fresh, sequence):
                try:
                    built = build_macro(game, table, "seat-1", macro.id)
                    if not isinstance(built, Reject):
                        run_op(table, "seat-1", built)
                except Exception as error:  # noqa: BLE001 - reported, not hidden
                    raise GameDefinitionError(
                        f"macro {macro.id!r} with {people} people raised "
                        f"{type(error).__name__}: {error}"
                    ) from error


def validate_games(root: Path = GAMES_ROOT) -> Report:
    """Load, cross-check and play every game under ``root``."""
    report = Report()
    catalog = {row["slug"]: row for row in read_rows(EXERCISES_CSV)}
    slugs: dict[str, str] = {}
    for directory in game_directories(root):
        try:
            game = load_game(directory)
        except GameDefinitionError as error:
            report.errors.append(str(error))
            continue
        report.checked.append(game.slug)
        if game.slug in slugs:
            report.errors.append(
                f"{directory.name}: slug {game.slug!r} is also used by "
                f"{slugs[game.slug]}/."
            )
        slugs[game.slug] = directory.name
        listed = catalog.get(game.slug)
        if game.definition.meta.listed:
            if listed is None:
                report.errors.append(
                    f"{directory.name}: listed, but content/{EXERCISES_CSV} "
                    f"has no row for {game.slug!r}."
                )
            elif listed["title"] != game.title:
                report.errors.append(
                    f"{directory.name}: title {game.title!r} does not match "
                    f"{listed['title']!r} in content/{EXERCISES_CSV}."
                )
        try:
            play_through(game)
        except GameDefinitionError as error:
            report.errors.append(f"{directory.name}: {error}")
    for slug in sorted(set(catalog) - set(slugs)):
        report.notes.append(
            f"{slug} is in content/{EXERCISES_CSV} but has no game definition "
            "yet; its tables start empty."
        )
    return report


__all__ = ["Report", "play_through", "validate_games"]
