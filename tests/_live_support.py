"""A live room wired to an in-memory database, for the realtime tests.

Not a test module itself. Everything here drives ``sandbox.web.live``
through its real entry points - a connection, a queue, a room task - so the
tests exercise the hub rather than a rehearsal of it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from _db_support import make_test_engine
from _model_support import build_sample_table
from sqlalchemy.orm import Session, sessionmaker

from sandbox.db.engine import session_scope
from sandbox.web import rooms
from sandbox.web.live import Connection, LiveHub, RoomRuntime

GAME_SLUG = "value-cards-trading"


@dataclass
class FakeSocket:
    """A socket that records what it was sent, and can refuse to read.

    ``blocked`` models the client this layer must survive: one that has
    stopped draining, so its outbound queue fills up.
    """

    sent: list[dict[str, Any]] = field(default_factory=list)
    blocked: bool = False
    _gate: asyncio.Event = field(default_factory=asyncio.Event)

    async def send_text(self, data: str) -> None:
        while self.blocked:
            self._gate.clear()
            await self._gate.wait()
        self.sent.append(json.loads(data))

    def unblock(self) -> None:
        self.blocked = False
        self._gate.set()

    def of_type(self, message_type: str) -> list[dict[str, Any]]:
        return [message for message in self.sent if message["type"] == message_type]

    def clear(self) -> None:
        self.sent.clear()


@dataclass
class Client:
    """One attached browser: its socket, its connection, and its writer task."""

    socket: FakeSocket
    connection: Connection
    writer: asyncio.Task[None]
    seat_id: str | None


class LiveFixture:
    """A room with a real table, a real hub, and however many clients."""

    def __init__(
        self, hub: LiveHub, runtime: RoomRuntime, factory: sessionmaker[Session]
    ) -> None:
        self.hub = hub
        self.runtime = runtime
        self.factory = factory
        self.clients: list[Client] = []

    async def connect(
        self,
        seat_id: str | None,
        *,
        display_name: str = "Someone",
        is_facilitator: bool = False,
        last_seq: int = 0,
    ) -> Client:
        socket = FakeSocket()
        connection, writer = await self.hub.attach(
            self.runtime,
            socket,
            participant_id=f"participant-{seat_id}",
            display_name=display_name,
            seat_id=seat_id,
            is_facilitator=is_facilitator,
            is_observer=seat_id is None,
        )
        client = Client(
            socket=socket, connection=connection, writer=writer, seat_id=seat_id
        )
        self.clients.append(client)
        await self.hello(client, last_seq=last_seq)
        return client

    async def hello(self, client: Client, *, last_seq: int = 0) -> None:
        await self.send(
            client,
            {"type": "hello", "room_code": self.runtime.code, "last_seq": last_seq},
        )

    async def intent(
        self,
        client: Client,
        op_type: str,
        payload: dict[str, Any] | None = None,
        *,
        client_id: str = "c1",
    ) -> None:
        await self.send(
            client,
            {
                "type": "intent",
                "client_id": client_id,
                "op_type": op_type,
                "payload": payload or {},
            },
        )

    async def send(self, client: Client, raw: dict[str, Any]) -> None:
        from sandbox.web.live import CLIENT_MESSAGE

        await self.runtime.submit(
            client.connection, CLIENT_MESSAGE.validate_python(raw)
        )

    async def settle(self, seconds: float = 0.3) -> None:
        """Let the room task drain its queue and run its periodic flushes."""
        await self.runtime.drain()
        deadline = asyncio.get_running_loop().time() + seconds
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)

    def events(self) -> list[tuple[int, str]]:
        """The room's permanent log, as ``(seq, op_type)`` pairs."""
        with session_scope(self.factory) as session:
            room = rooms.get_room(session, self.runtime.room_id)
            assert room is not None
            return [(event.seq, event.op_type) for event in room.events]


@asynccontextmanager
async def live_room(deck_size: int = 6) -> AsyncIterator[LiveFixture]:
    """A started room whose table is the shared sample table."""
    engine = make_test_engine()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with session_scope(factory) as session:
        room, _facilitator = rooms.create_room(
            session,
            game_slug=GAME_SLUG,
            facilitator_cookie_id="cookie-facilitator",
            facilitator_name="Facilitator",
        )
        session.flush()
        rooms.save_table_state(session, room, build_sample_table(deck_size=deck_size))
        code = room.code

    hub = LiveHub(session_factory=factory)
    runtime = await hub.runtime_for(code)
    assert runtime is not None
    fixture = LiveFixture(hub, runtime, factory)
    try:
        yield fixture
    finally:
        for client in fixture.clients:
            client.socket.unblock()
            await hub.detach(runtime, client.connection, client.writer)
        await hub.shutdown()
