"""The demo seed makes a begun activity with fake participants."""

from __future__ import annotations

import pytest
from _db_support import db_session

from sandbox.seed import SeedError, seed_demo
from sandbox.web import rooms


def test_seeds_value_cards_trading() -> None:
    with db_session() as session:
        code = seed_demo(session, "value-cards-trading")
        room = rooms.get_room_by_code(session, code)
        assert room is not None
        table = rooms.load_table(session, room)
        (activity,) = table.activities.values()
        assert activity.status == "running"
        assert len(activity.seats) == 3


def test_refuses_a_party_the_exercise_cannot_take() -> None:
    with db_session() as session:
        with pytest.raises(SeedError):
            seed_demo(session, "value-cards-trading", people=7)
        with pytest.raises(SeedError):
            seed_demo(session, "no-such-exercise")


def test_seeds_democracy_simulation() -> None:
    with db_session() as session:
        code = seed_demo(session, "democracy-simulation", people=9)
        room = rooms.get_room_by_code(session, code)
        assert room is not None
        (activity,) = rooms.load_table(session, room).activities.values()
        assert activity.status == "running"
        assert len(activity.seats) == 9
