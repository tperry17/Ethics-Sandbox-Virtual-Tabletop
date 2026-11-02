"""A demo room with fake participants, so an exercise can be shown without a group.

``uv run sandbox seed-demo value-cards-trading`` makes an open room, seats
people in it, opens the exercise as an activity, signs the seated people up
and begins it. The fake people have cookies nobody holds, so a real browser
that opens the printed link joins as one more observer and can take a seat
or the facilitator's chair.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from sandbox.games import GAMES, OPEN_ROOM_SLUG
from sandbox.games.engine import build_activity_start
from sandbox.model import JoinActivity, Ok, OpenActivity, Reject
from sandbox.web import rooms

DEMO_NAMES = (
    "Ada",
    "Boaz",
    "Chiara",
    "Dev",
    "Esi",
    "Farid",
    "Greta",
    "Hiro",
    "Ines",
    "Jomo",
    "Kavya",
    "Lena",
    "Mateo",
    "Noor",
    "Oren",
    "Priya",
    "Quinn",
    "Rosa",
    "Sami",
    "Tomas",
)


class SeedError(Exception):
    """The demo could not be made; the message says why."""


def seed_demo(session: Session, slug: str, *, people: int | None = None) -> str:
    """Create the demo room for ``slug`` and return its room code."""
    game = GAMES.get(slug)
    if game is None or slug == OPEN_ROOM_SLUG:
        raise SeedError(f"There is no exercise called {slug!r}.")
    meta = game.definition.meta
    count = meta.players.min if people is None else people
    if not meta.players.min <= count <= min(meta.players.max, len(DEMO_NAMES)):
        raise SeedError(
            f"{meta.title} takes {meta.players.min} to {meta.players.max} players "
            f"(this command can seat up to {len(DEMO_NAMES)})."
        )

    room, first = rooms.create_room(
        session,
        game_slug=OPEN_ROOM_SLUG,
        facilitator_cookie_id="demo-1",
        facilitator_name=DEMO_NAMES[0],
    )
    seated = [first]
    for index in range(1, count):
        seated.append(
            rooms.join_room(
                session,
                code=room.code,
                cookie_id=f"demo-{index + 1}",
                display_name=DEMO_NAMES[index],
            )
        )
    session.flush()
    seats = [person.seat_id for person in seated if person.seat_id]
    opened = rooms.apply_op(
        session,
        room,
        seats[0],
        OpenActivity(
            kind=meta.slug,
            title=meta.title,
            min_players=meta.players.min,
            max_players=meta.players.max,
            options=tuple(game.definition.default_options().items()),
        ),
    )
    if not isinstance(opened.outcome, Ok):
        raise SeedError(str(opened.outcome))
    table = rooms.load_table(session, room)
    activity_id = next(reversed(table.activities))
    for seat in seats[1:]:
        joined = rooms.apply_op(session, room, seat, JoinActivity(activity_id))
        if not isinstance(joined.outcome, Ok):
            raise SeedError(str(joined.outcome))
    built = build_activity_start(
        game, rooms.load_table(session, room), seats[0], activity_id
    )
    if isinstance(built, Reject):
        raise SeedError(str(built))
    begun = rooms.apply_op(session, room, seats[0], built)
    if not isinstance(begun.outcome, Ok):
        raise SeedError(str(begun.outcome))
    return room.code
