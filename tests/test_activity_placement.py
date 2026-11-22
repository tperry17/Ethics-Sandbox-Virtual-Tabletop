"""Where an activity's area is laid out: right below the room's own piles."""

from __future__ import annotations

from _games_support import seated

from sandbox.db.snapshot import from_snapshot, to_snapshot
from sandbox.games import GAMES
from sandbox.games.engine import ACTIVITY_GAP, ACTIVITY_SPACING, build_activity_start
from sandbox.model import (
    EndActivity,
    JoinActivity,
    Ok,
    OpenActivity,
    Rect,
    StartClass,
    Table,
    Transaction,
    run_op,
)

ROOM = GAMES["value-cards-room"]
TRADING = GAMES["value-cards-trading"]


def _rect(table: Table, zone_id: str) -> Rect:
    geometry = table.zones[zone_id].geometry
    assert isinstance(geometry, Rect)
    return geometry


def _begin(table: Table, activity_id: str) -> None:
    built = build_activity_start(TRADING, table, "seat-1", activity_id)
    assert isinstance(built, Transaction), built
    assert isinstance(run_op(table, "seat-1", built), Ok)


def test_an_activity_is_laid_out_right_below_the_rooms_piles() -> None:
    table = seated(ROOM, 3)
    meta = TRADING.definition.meta
    opened = OpenActivity(
        kind=meta.slug, title=meta.title, min_players=3, max_players=6
    )
    assert isinstance(run_op(table, "seat-1", opened), Ok)
    activity_id = next(reversed(table.activities))
    for seat in ("seat-2", "seat-3"):
        assert isinstance(run_op(table, seat, JoinActivity(activity_id)), Ok)
    _begin(table, activity_id)

    piles_bottom = max(
        _rect(table, zone).y + _rect(table, zone).height for zone in ("deck", "sidebar")
    )
    area = [_rect(table, zone) for zone in table.activities[activity_id].zones]
    top = min(rect.y for rect in area)
    # Its own table starts exactly one gap below the piles, at the room's left edge.
    assert top == piles_bottom + ACTIVITY_GAP
    assert min(rect.x for rect in area) == 0
    # Its deck sits under the room's Core deck, as the room's piles do above it.
    assert _rect(table, f"{activity_id}:deck").x == _rect(table, "deck").x


def test_a_class_lays_its_tables_side_by_side_and_each_keeps_its_place() -> None:
    table = seated(ROOM, 7)
    meta = TRADING.definition.meta
    started = StartClass(meta.slug, meta.title, 3, 6, tables=2)
    assert isinstance(run_op(table, "seat-1", started), Ok)
    first, second = next(reversed(table.classes.values())).tables
    for activity_id, seats in (
        (first, ("seat-2", "seat-3", "seat-4")),
        (second, ("seat-5", "seat-6", "seat-7")),
    ):
        for seat in seats:
            assert isinstance(run_op(table, seat, JoinActivity(activity_id)), Ok)
        _begin(table, activity_id)
    left = _rect(table, f"{first}:table")
    right = _rect(table, f"{second}:table")
    assert right.y == left.y
    assert right.x - left.x == ACTIVITY_SPACING

    # The first table ends; the second stays in its own column, and a saved
    # and reloaded table remembers where the class began.
    assert isinstance(run_op(table, "seat-1", EndActivity(first)), Ok)
    reloaded = from_snapshot(to_snapshot(table))
    group = next(iter(reloaded.classes.values()))
    assert group.first_serial == int(first.rsplit("-", 1)[1])
    assert _rect(reloaded, f"{second}:table").x == right.x
