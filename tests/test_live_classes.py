"""A class in a live room: who may run it, what each person is sent, what it changes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from _db_support import make_test_engine
from _live_support import Client
from sqlalchemy.orm import sessionmaker
from test_live_macros import GameRoom

from sandbox.db.engine import session_scope
from sandbox.web import rooms
from sandbox.web.live import LiveHub

HOST = "cookie-host"


@asynccontextmanager
async def open_room(
    guests: int, kind: str = "test-room"
) -> AsyncIterator[tuple[GameRoom, Client, list[Client]]]:
    engine = make_test_engine()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_scope(factory) as session:
        room, _ = rooms.create_room(
            session,
            game_slug=kind,
            facilitator_cookie_id=HOST,
            facilitator_name="Ines",
        )
        code = room.code
    hub = LiveHub(session_factory=factory)
    runtime = await hub.runtime_for(code)
    assert runtime is not None
    fixture = GameRoom(hub, runtime, factory)
    try:
        host = await fixture.arrive(HOST)
        people: list[Client] = []
        for number in range(guests):
            fixture.join(f"cookie-{number}", f"Guest {number}")
            people.append(await fixture.arrive(f"cookie-{number}"))
            # Let the room save before the next person sits, so the test's own
            # database write never races the room's.
            await fixture.settle()
        yield fixture, host, people
    finally:
        for client in fixture.clients:
            client.socket.unblock()
            await hub.detach(runtime, client.connection, client.writer)
        await hub.shutdown()


async def _act(
    room: GameRoom, who: Client, payload: dict[str, Any], client_id: str = "k"
) -> None:
    await room.intent(who, "class", payload, client_id=client_id)
    await room.settle(0.05)


def _classes(client: Client) -> list[dict[str, Any]]:
    classes: list[dict[str, Any]] = client.socket.of_type("snapshot")[-1]["classes"]
    return classes


async def test_whoever_starts_a_class_becomes_its_facilitator_and_does_not_sit() -> (
    None
):
    async with open_room(6) as (room, host, guests):
        await _act(
            room, host, {"action": "start", "slug": "pairs", "tables": 3}, "start"
        )
        assert host.socket.of_type("ack")[-1]["client_id"] == "start"
        table = room.runtime.table
        assert table.is_facilitator(host.seat_id or "")
        (group,) = table.classes.values()
        assert len(group.tables) == 3
        assert all(table.activities[t].seats == () for t in group.tables)
        assert [c["id"] for c in _classes(guests[0])] == [group.id]


async def test_someone_else_holds_the_seat_so_a_guest_cannot_start_a_class() -> None:
    async with open_room(2) as (room, host, guests):
        await _act(room, host, {"action": "start", "slug": "pairs", "tables": 2})
        await _act(room, guests[0], {"action": "start", "slug": "pairs", "tables": 2})
        assert (
            "Only the facilitator" in guests[0].socket.of_type("reject")[-1]["reason"]
        )
        assert len(room.runtime.table.classes) == 1


async def test_a_guest_cannot_run_the_class() -> None:
    async with open_room(4) as (room, host, guests):
        await _act(room, host, {"action": "start", "slug": "pairs", "tables": 2})
        class_id = next(iter(room.runtime.table.classes))
        for action in (
            {"action": "timer", "seconds": 60},
            {"action": "prompt", "prompt_id": ""},
            {"action": "sort_preview"},
            {"action": "begin"},
            {"action": "end"},
        ):
            await _act(room, guests[0], {"class_id": class_id, **action})
            assert guests[0].socket.of_type("reject")[-1]["reason"].startswith("Only")
        assert guests[0].socket.of_type("class_sort") == []
        assert class_id in room.runtime.table.classes


async def test_sort_preview_is_the_facilitators_and_confirming_seats_people() -> None:
    async with open_room(4) as (room, host, guests):
        await _act(room, host, {"action": "start", "slug": "pairs", "tables": 2})
        class_id = next(iter(room.runtime.table.classes))
        await _act(room, host, {"action": "sort_preview", "class_id": class_id})
        (proposal,) = host.socket.of_type("class_sort")
        assert all(c.socket.of_type("class_sort") == [] for c in guests)
        assert sorted(s for t in proposal["tables"] for s in t) == sorted(
            c.seat_id or "" for c in guests
        )
        assert [len(t) for t in proposal["tables"]] == [2, 2]
        # Nothing is seated until it is confirmed.
        assert all(a.seats == () for a in room.runtime.table.activities.values())

        await _act(
            room,
            host,
            {"action": "assign", "class_id": class_id, "tables": proposal["tables"]},
        )
        seated = [a.seats for a in room.runtime.table.activities.values()]
        assert seated == [tuple(t) for t in proposal["tables"]]

        await _act(room, host, {"action": "begin", "class_id": class_id})
        assert {a.status for a in room.runtime.table.activities.values()} == {"running"}


async def test_the_timer_reaches_every_screen_and_changes_nothing_on_the_table() -> (
    None
):
    async with open_room(4) as (room, host, guests):
        await _act(room, host, {"action": "start", "slug": "pairs", "tables": 2})
        class_id = next(iter(room.runtime.table.classes))
        pieces = dict(room.runtime.table.pieces)
        await _act(room, host, {"action": "timer", "class_id": class_id, "seconds": 90})
        for client in (host, *guests):
            (view,) = _classes(client)
            assert 80 < view["timer_remaining"] <= 90
        await _act(
            room, host, {"action": "prompt", "class_id": class_id, "prompt_id": ""}
        )
        assert room.runtime.table.pieces == pieces


async def test_pairing_is_for_scenario_two_and_its_outcome_is_the_facilitators() -> (
    None
):
    async with open_room(2, "democracy-room") as (room, host, guests):
        await _act(
            room,
            host,
            {
                "action": "start",
                "slug": "scenario-2",
                "tables": 2,
                "options": {"city": "potamosia", "phase": "2"},
            },
        )
        class_id = next(iter(room.runtime.table.classes))
        a, b = room.runtime.table.classes[class_id].tables
        pair = {"class_id": class_id, "first": a, "second": b}
        await _act(room, host, {"action": "pair", **pair})
        await _act(
            room,
            host,
            {
                "action": "decision",
                "class_id": class_id,
                "first": a,
                "decision": "Attack",
            },
        )
        await _act(
            room,
            host,
            {
                "action": "decision",
                "class_id": class_id,
                "first": b,
                "decision": "Diplomacy",
            },
        )
        (view,) = _classes(host)
        assert view["can_pair"] is True
        assert view["pairs"][0]["outcome"].startswith("Catastrophic for the defender")
        # A guest is sent no pairing, decision or outcome.
        (seen,) = _classes(guests[0])
        assert seen["pairs"] == [] and seen["pair_choices"] == []
        assert "Catastrophic" not in str(guests[0].socket.of_type("snapshot")[-1])

        await _act(
            room,
            host,
            {
                "action": "decision",
                "class_id": class_id,
                "first": a,
                "decision": "Nuke",
            },
        )
        assert "not a choice" in host.socket.of_type("reject")[-1]["reason"]


async def test_scenario_one_and_other_activities_refuse_pairing() -> None:
    async with open_room(2, "democracy-room") as (room, host, _guests):
        await _act(
            room,
            host,
            {
                "action": "start",
                "slug": "scenario-1",
                "tables": 2,
                "options": {"city": "potamosia", "phase": "1"},
            },
        )
        class_id = next(iter(room.runtime.table.classes))
        a, b = room.runtime.table.classes[class_id].tables
        await _act(
            room,
            host,
            {"action": "pair", "class_id": class_id, "first": a, "second": b},
        )
        assert host.socket.of_type("reject")[-1]["reason"] == (
            "This activity does not pair tables."
        )


async def test_someone_who_arrives_after_the_sort_takes_the_roomiest_table() -> None:
    async with open_room(3) as (room, host, guests):
        await _act(room, host, {"action": "start", "slug": "pairs", "tables": 2})
        class_id = next(iter(room.runtime.table.classes))
        first, second = room.runtime.table.classes[class_id].tables
        await _act(
            room,
            host,
            {
                "action": "assign",
                "class_id": class_id,
                "tables": [[guests[0].seat_id], [guests[1].seat_id]],
            },
        )
        await room.settle()
        room.join("cookie-late", "Late")
        late = await room.arrive("cookie-late")
        await asyncio.sleep(0.05)
        await room.settle()
        activities = room.runtime.table.activities
        assert late.seat_id in activities[first].seats + activities[second].seats
        assert len(activities[first].seats) + len(activities[second].seats) == 3


async def test_a_latecomer_takes_the_roomiest_table_after_others_have_begun() -> None:
    async with open_room(4) as (room, host, guests):
        await _act(room, host, {"action": "start", "slug": "pairs", "tables": 2})
        class_id = next(iter(room.runtime.table.classes))
        first, second = room.runtime.table.classes[class_id].tables
        seats = [c.seat_id for c in guests]
        await _act(
            room,
            host,
            {
                "action": "assign",
                "class_id": class_id,
                "tables": [[seats[0], seats[1]], [seats[2]]],
            },
        )
        await _act(room, host, {"action": "begin", "class_id": class_id})
        await room.settle()
        assert room.runtime.table.activities[first].status == "running"
        room.join("cookie-late", "Late")
        late = await room.arrive("cookie-late")
        await room.settle()
        table = room.runtime.table
        # The first table is full and running; the second had room.
        assert table.activities[second].seats == (seats[2], late.seat_id)
        assert table.activities[first].status == "running"


async def test_the_facilitator_moves_people_and_a_guest_cannot() -> None:
    async with open_room(4) as (room, host, guests):
        await _act(room, host, {"action": "start", "slug": "pairs", "tables": 2})
        class_id = next(iter(room.runtime.table.classes))
        first, second = room.runtime.table.classes[class_id].tables
        a, b, c, d = (g.seat_id for g in guests)
        await _act(
            room,
            host,
            {"action": "assign", "class_id": class_id, "tables": [[a, b], [c]]},
        )
        await _act(room, host, {"action": "begin", "class_id": class_id})
        move = {"action": "move", "class_id": class_id, "seat_id": a, "to": second}
        await _act(room, guests[1], move)
        assert guests[1].socket.of_type("reject")[-1]["reason"].startswith("Only")
        await _act(room, host, move)
        table = room.runtime.table
        assert table.activities[first].seats == (b,)
        assert table.activities[second].seats == (c, a)
        assert f"{first}:hand-{a}" not in table.zones  # it left the begun table
        await _act(room, host, {**move, "seat_id": d, "to": second})
        assert host.socket.of_type("reject")[-1]["reason"]  # the table is full


async def test_players_at_a_paired_table_pick_its_choice_and_see_only_that() -> None:
    async with open_room(4, "democracy-room") as (room, host, guests):
        await _act(
            room,
            host,
            {
                "action": "start",
                "slug": "scenario-2",
                "tables": 2,
                "options": {"city": "potamosia", "phase": "2"},
            },
        )
        class_id = next(iter(room.runtime.table.classes))
        a, b = room.runtime.table.classes[class_id].tables
        mine, theirs = guests[0], guests[1]
        # Seat one person at each table (no need to begin).
        await _act(
            room,
            host,
            {"action": "pair", "class_id": class_id, "first": a, "second": b},
        )
        await _act(
            room,
            host,
            {
                "action": "assign",
                "class_id": class_id,
                "tables": [[mine.seat_id], [theirs.seat_id]],
            },
        )
        (view,) = _classes(mine)
        assert view["your_table"] == a and view["pair_choices"]
        decide = {
            "action": "decision",
            "class_id": class_id,
            "first": a,
            "decision": "Attack",
        }
        await _act(room, mine, decide)
        assert mine.socket.of_type("ack")
        (view,) = _classes(mine)
        assert view["your_proposal"] == "Attack"
        assert view["your_decision"] is None  # waiting for the facilitator
        (seen,) = _classes(host)
        assert seen["pairs"][0]["first_proposed"] == "Attack"
        assert seen["pairs"][0]["first_decision"] is None
        await _act(room, host, decide)
        (view,) = _classes(mine)
        assert view["your_decision"] == "Attack" and view["your_proposal"] is None
        # Their partner's table sees nothing of it, and nobody else may set it.
        (other,) = _classes(theirs)
        assert other["your_decision"] is None and other["pairs"] == []
        await _act(room, theirs, {**decide, "decision": "Diplomacy"})
        assert theirs.socket.of_type("reject")
        assert "'your_decision': 'Attack'" not in str(
            theirs.socket.of_type("snapshot")[-1]
        )
        assert room.runtime.table.classes[class_id].decisions == {a: "Attack"}
