"""Room types: one per exercise, each its own sandbox with its own activities.

A room type is a game definition with a ``room:`` section. Its table is the
room's sandbox; its ``room.activities`` are the only activities the room
offers, each a game with some options perhaps fixed. Nothing here knows any
exercise by name.
"""

from __future__ import annotations

from dataclasses import dataclass

from sandbox.games.definition import RoomActivity
from sandbox.games.loader import Game


@dataclass(frozen=True)
class OfferedActivity:
    """One activity a room offers, resolved to its game."""

    id: str
    title: str
    game: Game
    fixed: dict[str, str]
    class_only: bool


def room_types(games: dict[str, Game]) -> list[Game]:
    """Every room type, in the order the games were loaded."""
    return [game for game in games.values() if game.definition.room is not None]


def room_for_exercise(games: dict[str, Game], exercise_slug: str) -> Game | None:
    """The room type whose page is ``exercise_slug``'s, if it has one."""
    return next(
        (
            game
            for game in room_types(games)
            if game.definition.room is not None
            and game.definition.room.exercise == exercise_slug
        ),
        None,
    )


def _resolve(games: dict[str, Game], activity: RoomActivity) -> OfferedActivity | None:
    game = games.get(activity.game)
    if game is None or game.definition.room is not None:
        return None
    return OfferedActivity(
        id=activity.id,
        title=activity.title or game.title,
        game=game,
        fixed=dict(activity.options),
        class_only=activity.class_only,
    )


def offered_activities(
    games: dict[str, Game], room_game: Game | None
) -> list[OfferedActivity]:
    """What a room of ``room_game`` can start, in the order it lists them."""
    if room_game is None or room_game.definition.room is None:
        return []
    offered = (_resolve(games, a) for a in room_game.definition.room.activities)
    return [activity for activity in offered if activity is not None]


def offered_activity(
    games: dict[str, Game], room_game: Game | None, activity_id: object
) -> OfferedActivity | None:
    """The activity ``activity_id`` names in this room, or None."""
    return next(
        (a for a in offered_activities(games, room_game) if a.id == activity_id),
        None,
    )


__all__ = [
    "OfferedActivity",
    "offered_activities",
    "offered_activity",
    "room_for_exercise",
    "room_types",
]
