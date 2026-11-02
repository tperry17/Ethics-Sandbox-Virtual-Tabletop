"""Golden tests: starting each exercise lays out the table it is meant to.

The expected layout is a JSON file under ``tests/golden/``: each zone, with
its kind, visibility, owner and what rests in it (counted by piece kind).
Card faces are not recorded; their order is random and secret. After an
intended change to an exercise, regenerate with
``UPDATE_GOLDEN=1 uv run pytest tests/test_golden_setup.py`` and read the diff.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from sandbox.games import GAMES
from sandbox.games.engine import build_activity_start, build_seat, build_table
from sandbox.model import (
    JoinActivity,
    Ok,
    OpenActivity,
    Table,
    TableRng,
    Transaction,
    run_op,
)

GOLDEN = Path(__file__).parent / "golden"
Options = tuple[tuple[str, str], ...]
CASES: list[tuple[str, str, Options]] = [
    ("value-cards-trading", "value-cards-trading", ()),
    (
        "democracy-simulation",
        "democracy-simulation-potamosia-1",
        (("city", "potamosia"), ("phase", "1")),
    ),
    (
        "democracy-simulation",
        "democracy-simulation-hudrosia-2",
        (("city", "hudrosia"), ("phase", "2")),
    ),
]


def _started(slug: str, options: Options) -> Table:
    game = GAMES[slug]
    meta = game.definition.meta
    table = Table(rng=TableRng(seed=11))
    seat_id, transaction = build_table(None, table, participant_id="p-1")
    assert isinstance(run_op(table, seat_id, transaction), Ok)
    for person in range(2, meta.players.min + 1):
        seat_id, transaction = build_seat(None, table, participant_id=f"p-{person}")
        assert isinstance(run_op(table, seat_id, transaction), Ok)
    opened = OpenActivity(
        kind=slug,
        title=meta.title,
        min_players=meta.players.min,
        max_players=meta.players.max,
        options=options,
    )
    assert isinstance(run_op(table, "seat-1", opened), Ok)
    activity_id = next(reversed(table.activities))
    for number in range(2, meta.players.min + 1):
        assert isinstance(
            run_op(table, f"seat-{number}", JoinActivity(activity_id)), Ok
        )
    built = build_activity_start(game, table, "seat-1", activity_id)
    assert isinstance(built, Transaction), built
    assert isinstance(run_op(table, "seat-1", built), Ok)
    return table


def _layout(table: Table) -> dict[str, Any]:
    zones: dict[str, Any] = {}
    for zone_id, zone in sorted(table.zones.items()):
        kinds = Counter(
            piece.kind.value
            for piece in table.pieces.values()
            if piece.zone_id == zone_id
        )
        zones[zone_id] = {
            "kind": zone.kind.value,
            "visibility": zone.visibility.value,
            "owner_seat": zone.owner_seat,
            "pieces": dict(sorted(kinds.items())),
        }
    return {"zones": zones, "seats": sorted(table.seats)}


@pytest.mark.parametrize(("slug", "name", "options"), CASES)
def test_starting_an_exercise_lays_out_the_expected_table(
    slug: str, name: str, options: Options
) -> None:
    layout = _layout(_started(slug, options))
    path = GOLDEN / f"{name}.json"
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(json.dumps(layout, indent=2, sort_keys=True) + "\n")
    expected = json.loads(path.read_text())
    assert layout == expected
