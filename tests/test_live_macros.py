"""Macro buttons and late seats in a live room built from a game definition."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from _db_support import make_test_engine
from _live_support import Client, FakeSocket, LiveFixture
from sqlalchemy.orm import sessionmaker

from sandbox.db.engine import session_scope
from sandbox.db.models import Event, TableState
from sandbox.db.snapshot import from_snapshot
from sandbox.model import Table
from sandbox.web import rooms
from sandbox.web.live import LiveHub, _load_participant

FACILITATOR_COOKIE = "cookie-facilitator"
GUEST_COOKIE = "cookie-guest"


class GameRoom(LiveFixture):
    """A live Two Doors room whose people connect the way a browser does."""

    async def arrive(self, cookie_id: str) -> Client:
        loaded = await asyncio.to_thread(
            _load_participant, self.factory, self.runtime.code, cookie_id
        )
        assert loaded is not None
        room, participant, stored_seat = loaded
        socket = FakeSocket()
        connection, writer = await self.hub.attach(
            self.runtime,
            socket,
            participant_id=participant.id,
            display_name=participant.display_name,
            seat_id=participant.seat_id,
            is_facilitator=room.facilitator_participant_id == participant.id,
            is_observer=participant.is_observer,
            stored_seat=stored_seat,
        )
        client = Client(
            socket=socket,
            connection=connection,
            writer=writer,
            seat_id=participant.seat_id,
        )
        self.clients.append(client)
        await self.hello(client)
        return client

    def join(self, cookie_id: str, name: str) -> None:
        with session_scope(self.factory) as session:
            rooms.join_room(
                session, code=self.runtime.code, cookie_id=cookie_id, display_name=name
            )

    async def press(self, client: Client, macro_id: str, *, op_id: str = "") -> None:
        payload: dict[str, Any] = {"macro_id": macro_id}
        if op_id:
            payload["op_id"] = op_id
        await self.intent(client, "macro", payload, client_id=f"press-{macro_id}")
        await self.settle()

    def logged(self) -> list[tuple[str, str]]:
        with session_scope(self.factory) as session:
            events = session.query(Event).order_by(Event.seq).all()
            return [
                (event.op_type, str(event.payload.get("name", ""))) for event in events
            ]


@asynccontextmanager
async def two_doors_room() -> AsyncIterator[GameRoom]:
    engine = make_test_engine()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_scope(factory) as session:
        room, _facilitator = rooms.create_room(
            session,
            game_slug="two-doors",
            facilitator_cookie_id=FACILITATOR_COOKIE,
            facilitator_name="Ines",
            as_facilitator=True,
        )
        code = room.code
    hub = LiveHub(session_factory=factory)
    runtime = await hub.runtime_for(code)
    assert runtime is not None
    fixture = GameRoom(hub, runtime, factory)
    try:
        yield fixture
    finally:
        for client in fixture.clients:
            client.socket.unblock()
            await hub.detach(runtime, client.connection, client.writer)
        await hub.shutdown()


async def _two_seated(room: GameRoom) -> tuple[Client, Client]:
    host = await room.arrive(FACILITATOR_COOKIE)
    room.join(GUEST_COOKIE, "Tomas")
    guest = await room.arrive(GUEST_COOKIE)
    await room.settle()
    return host, guest


def _faces_received(client: Client) -> set[str]:
    faces: set[str] = set()
    for message in client.socket.sent:
        for component in message.get("components", []) or []:
            faces.add(component["id"])
    return faces


# -- the toolbar ------------------------------------------------------------------


async def test_the_snapshot_carries_the_exercises_buttons_and_no_deck_faces() -> None:
    async with two_doors_room() as room:
        host = await room.arrive(FACILITATOR_COOKIE)
        await room.settle()

        snapshot = host.socket.of_type("snapshot")[-1]
        assert [macro["id"] for macro in snapshot["macros"]] == [
            "setup",
            "deal",
            "reveal",
            "reset",
            "shuffle",
            "collect",
            "clear_ink",
        ]
        reset = next(m for m in snapshot["macros"] if m["id"] == "reset")
        assert reset["confirm"].startswith("This removes every card")
        assert snapshot["components"] == []


async def test_a_seat_taken_while_the_room_is_live_reaches_its_table() -> None:
    async with two_doors_room() as room:
        host, guest = await _two_seated(room)

        assert "seat-2" in room.runtime.table.seats
        assert "hand-seat-2" in room.runtime.table.zones
        # Everyone already there is sent the new outline whole.
        zones = [
            zone["id"]
            for zone in host.socket.of_type("snapshot")[-1]["view_table"]["zones"]
        ]
        assert "hand-seat-2" in zones
        assert guest.seat_id == "seat-2"


async def test_pressing_deal_sends_each_person_only_their_own_card() -> None:
    async with two_doors_room() as room:
        host, guest = await _two_seated(room)

        await room.press(host, "deal")

        assert host.socket.of_type("ack")[-1]["client_id"] == "press-deal"
        mine = room.runtime.table.pieces_in_zone("hand-seat-1")[0].component_id
        theirs = room.runtime.table.pieces_in_zone("hand-seat-2")[0].component_id
        assert _faces_received(host) == {mine}
        assert _faces_received(guest) == {theirs}
        notices = [n["text"] for n in guest.socket.of_type("notice")]
        assert "Ines dealt one card to each seat." in notices


async def test_a_macro_is_one_event_in_the_log_and_one_snapshot() -> None:
    async with two_doors_room() as room:
        host, _guest = await _two_seated(room)

        await room.press(host, "deal")

        assert room.logged() == [
            ("Transaction", "setup"),
            ("Transaction", "seat:seat-2"),
            ("Transaction", "macro:deal"),
        ]
        with session_scope(room.factory) as session:
            state = session.get(TableState, room.runtime.room_id)
            assert state is not None
            stored = from_snapshot(state.snapshot)
        assert len(stored.pieces_in_zone("hand-seat-2")) == 1


async def test_a_repeated_press_is_applied_once() -> None:
    async with two_doors_room() as room:
        host, _guest = await _two_seated(room)

        await room.press(host, "deal", op_id="the-same-press")
        await room.press(host, "deal", op_id="the-same-press")

        assert len(room.runtime.table.pieces_in_zone("hand-seat-1")) == 1
        assert [name for _op, name in room.logged()].count("macro:deal") == 1


async def test_a_refused_macro_comes_back_as_a_sentence_and_changes_nothing() -> None:
    async with two_doors_room() as room:
        host, guest = await _two_seated(room)
        version = room.runtime.table.version

        await room.press(guest, "reset")
        await room.press(host, "reveal")

        assert guest.socket.of_type("reject")[-1]["reason"] == (
            "Only the facilitator can use “Reset”."
        )
        assert host.socket.of_type("reject")[-1]["reason"] == (
            "First seat has no card to reveal. Deal first."
        )
        assert room.runtime.table.version == version


async def test_a_seat_the_live_room_has_not_seen_survives_its_snapshot() -> None:
    async with two_doors_room() as room:
        host = await room.arrive(FACILITATOR_COOKIE)
        room.join(GUEST_COOKIE, "Tomas")  # sits down, has not connected yet

        await room.press(host, "deal")  # a macro writes a snapshot

        with session_scope(room.factory) as session:
            state = session.get(TableState, room.runtime.room_id)
            assert state is not None
            stored = from_snapshot(state.snapshot)
        assert "seat-2" in stored.seats
        assert "hand-seat-2" in stored.zones


async def test_a_seat_reaches_the_live_table_as_soon_as_it_is_taken() -> None:
    async with two_doors_room() as room:
        host = await room.arrive(FACILITATOR_COOKIE)
        room.join(GUEST_COOKIE, "Tomas")
        with session_scope(room.factory) as session:
            db_room = rooms.get_room_by_code(session, room.runtime.code)
            assert db_room is not None
            guest = rooms.get_participant(session, db_room.id, GUEST_COOKIE)
            assert guest is not None
            guest_id = guest.id

        # Their page has not connected yet, and the deal still includes them.
        await room.hub.seat_taken(room.runtime.code, guest_id)
        await room.press(host, "deal")

        assert len(room.runtime.table.pieces_in_zone("hand-seat-2")) == 1


# -- what survives a live room ------------------------------------------------------


def _stored(room: GameRoom) -> Table:
    with session_scope(room.factory) as session:
        state = session.get(TableState, room.runtime.room_id)
        assert state is not None
        return from_snapshot(state.snapshot)


async def test_the_table_is_saved_as_it_was_left_when_the_last_person_goes() -> None:
    async with two_doors_room() as room:
        host = await room.arrive(FACILITATOR_COOKIE)
        await room.press(host, "deal")
        card = room.runtime.table.pieces_in_zone("hand-seat-1")[0].id
        await room.intent(host, "grab", {"piece_id": card}, client_id="g")
        await room.intent(
            host, "move", {"piece_id": card, "x": 11, "y": 22}, client_id="m"
        )
        await room.settle()
        assert _stored(room).pieces[card].x != 11  # only the deal's snapshot so far

        room.clients.remove(host)
        await room.hub.detach(room.runtime, host.connection, host.writer)

        assert (_stored(room).pieces[card].x, _stored(room).pieces[card].y) == (11, 22)


async def test_a_seat_change_made_while_the_room_is_live_reaches_it_and_is_kept() -> (
    None
):
    async with two_doors_room() as room:
        host, guest = await _two_seated(room)
        with session_scope(room.factory) as session:
            db_room = rooms.get_room_by_code(session, room.runtime.code)
            assert db_room is not None
            leaving = rooms.get_participant(session, db_room.id, GUEST_COOKIE)
            assert leaving is not None
            rooms.release_seat(session, db_room, leaving)

        await room.hub.seats_changed(room.runtime.code)
        await room.press(host, "deal")  # a macro writes a snapshot

        assert room.runtime.table.seats["seat-2"].participant_id is None
        assert _stored(room).seats["seat-2"].participant_id is None
