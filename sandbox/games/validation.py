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

from sandbox.content_loading import CONTENT_ROOT, read_rows
from sandbox.games.engine import build_macro, build_seat, build_table
from sandbox.games.loader import (
    GAMES_ROOT,
    Game,
    GameDefinitionError,
    game_directories,
    load_game,
)
from sandbox.model import Reject, Table, TableRng, run_op
from sandbox.model.types import PieceKind, Visibility, ZoneKind

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


def validate_games(
    root: Path = GAMES_ROOT,
    content_root: Path = CONTENT_ROOT,
    *,
    catalog_notes: bool = True,
) -> Report:
    """Load, cross-check and play every game under ``root``.

    ``catalog_notes`` adds a note for each catalog exercise with no game
    here; it is off for a folder of extra games, which the catalog is not
    about.
    """
    report = Report()
    catalog = {row["slug"]: row for row in read_rows(EXERCISES_CSV)}
    slugs: dict[str, str] = {}
    loaded: dict[str, Game] = {}
    for directory in game_directories(root):
        try:
            game = load_game(directory, content_root)
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
        loaded[game.slug] = game
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
    report.errors.extend(_room_errors(loaded, catalog, whole_catalog=catalog_notes))
    for slug in sorted(set(catalog) - set(slugs)) if catalog_notes else ():
        report.notes.append(
            f"{slug} is in content/{EXERCISES_CSV} but has no game definition "
            "yet; its tables start empty."
        )
    return report


def _room_errors(
    games: dict[str, Game], catalog: dict[str, dict[str, str]], *, whole_catalog: bool
) -> list[str]:
    """What is wrong with the room types: their exercise and their activities.

    Each room names a catalog exercise, and every activity it offers is a
    game here with only real options fixed. With ``whole_catalog``, every
    catalog exercise has exactly one room.
    """
    errors: list[str] = []
    rooms_for: dict[str, list[str]] = {}
    for game in games.values():
        room = game.definition.room
        if room is None:
            continue
        rooms_for.setdefault(room.exercise, []).append(game.slug)
        # Every room gives each seat a private hand, so cards can always be
        # dealt to people for their eyes only.
        if not any(
            zone.kind is ZoneKind.HAND
            and zone.per_seat
            and zone.visibility is Visibility.PRIVATE_TO_OWNER
            for zone in game.definition.zones
        ):
            errors.append(f"{game.slug}: a room needs a private, per-seat hand zone.")
        # Shared writing is put on the table as one of the room's notes.
        if not any(
            piece.kind is PieceKind.NOTE for piece in game.definition.components.pieces
        ):
            errors.append(f"{game.slug}: a room needs a note piece for shared writing.")
        if whole_catalog and room.exercise not in catalog:
            errors.append(
                f"{game.slug}: is the room for {room.exercise!r}, which is not "
                f"in content/{EXERCISES_CSV}."
            )
        for activity in room.activities:
            target = games.get(activity.game)
            if target is None or target.definition.room is not None:
                errors.append(
                    f"{game.slug}: activity {activity.id!r} names {activity.game!r}, "
                    "which is not an activity's game."
                )
                continue
            for option_id, choice_id in activity.options.items():
                option = next(
                    (o for o in target.definition.options if o.id == option_id), None
                )
                if option is None or choice_id not in {c.id for c in option.choices}:
                    errors.append(
                        f"{game.slug}: activity {activity.id!r} fixes "
                        f"{option_id}={choice_id}, which {activity.game!r} "
                        "does not offer."
                    )
    for exercise, rooms in sorted(rooms_for.items()):
        if len(rooms) > 1:
            errors.append(f"{exercise} has more than one room: {sorted(rooms)}.")
    if whole_catalog:
        for slug in sorted(set(catalog) - set(rooms_for)):
            errors.append(f"{slug} is in content/{EXERCISES_CSV} but has no room.")
    return errors


__all__ = ["Report", "play_through", "validate_games"]
