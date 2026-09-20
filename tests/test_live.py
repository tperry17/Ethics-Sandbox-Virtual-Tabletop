"""The realtime layer: ordering, reconnect, rejection, backpressure, and the
one rule that matters most - nothing leaves the server unprojected.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from _db_support import make_test_engine
from _live_support import live_room
from _model_support import DECK, HAND_A, PUBLIC_TABLE, SEAT_A, SEAT_B
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from starlette.websockets import WebSocketDisconnect

from sandbox.db.engine import session_scope
from sandbox.db.models import TableState
from sandbox.db.snapshot import from_snapshot
from sandbox.model import Move, MoveToZone, Table
from sandbox.web import live
from sandbox.web.app import app, get_session


def _patch_seqs(socket: Any) -> list[int]:
    return [message["seq"] for message in socket.of_type("patches")]


def _pieces_in(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every piece-shaped payload in a list of outbound messages."""
    found: list[dict[str, Any]] = []
    for message in messages:
        if message["type"] == "snapshot":
            found.extend(message["view_table"]["pieces"])
        if message["type"] == "patches":
            found.extend(
                patch["fields"] | {"id": patch["entity_id"]}
                for patch in message["patches"]
                if patch["kind"] == "piece" and patch["op"] == "upsert"
            )
    return found


# -- the wire protocol -----------------------------------------------------------------


def test_every_operation_has_a_wire_name() -> None:
    assert live.OPERATIONS["move_to_zone"] is MoveToZone
    assert live.OPERATIONS["move"] is Move
    assert len(live.OPERATIONS) == 28


def test_decode_intent_reads_a_payload_into_an_operation() -> None:
    operation = live.decode_intent("move", {"piece_id": "card-1", "x": 4, "y": 5})
    assert isinstance(operation, Move)
    assert (operation.x, operation.y) == (4.0, 5.0)


def test_decode_intent_refuses_an_unknown_operation() -> None:
    with pytest.raises(live.IntentError, match="no operation called"):
        live.decode_intent("delete_everything", {})


def test_decode_intent_explains_a_bad_payload_in_a_sentence() -> None:
    with pytest.raises(live.IntentError, match="could not be read"):
        live.decode_intent("move", {"piece_id": "card-1"})


# -- ordering and sequence numbers -----------------------------------------------------


async def test_the_server_assigns_sequence_numbers_in_order() -> None:
    async with live_room() as room:
        watcher = await room.connect(SEAT_B, display_name="Bo")
        actor = await room.connect(SEAT_A, display_name="Ana")
        watcher.socket.clear()

        await room.intent(
            actor, "draw", {"count": 1, "from_zone": DECK, "to_zone": HAND_A}
        )
        await room.intent(
            actor, "draw", {"count": 1, "from_zone": DECK, "to_zone": HAND_A}
        )
        await room.settle()

        seqs = _patch_seqs(watcher.socket)
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)


async def test_a_repeated_intent_is_applied_once() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        payload = {
            "count": 1,
            "from_zone": DECK,
            "to_zone": HAND_A,
            "op_id": "the-same-op",
        }

        await room.intent(actor, "draw", payload)
        await room.settle(0.1)
        await room.intent(actor, "draw", payload)
        await room.settle()

        drawn = [
            piece
            for piece in room.runtime.table.pieces.values()
            if piece.zone_id == HAND_A
        ]
        assert len(drawn) == 1
        assert [op for _seq, op in room.events()] == ["Draw"]


# -- rejection -------------------------------------------------------------------------


async def test_a_rejected_intent_comes_back_as_a_readable_sentence() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")

        await room.intent(actor, "reset_table", {})
        await room.settle()

        rejects = actor.socket.of_type("reject")
        assert rejects
        assert rejects[-1]["reason"] == "Only the facilitator may reset the table."
        assert rejects[-1]["client_id"] == "c1"


async def test_an_observer_may_watch_but_not_act() -> None:
    async with live_room() as room:
        observer = await room.connect(None, display_name="Visitor")

        await room.intent(observer, "shuffle", {"zone_id": DECK})
        await room.settle()

        assert observer.socket.of_type("reject")[-1]["reason"] == (
            "Observers can watch but not act."
        )


async def test_two_seats_grabbing_the_same_piece_in_one_tick() -> None:
    async with live_room() as room:
        first = await room.connect(SEAT_A, display_name="Ana")
        second = await room.connect(SEAT_B, display_name="Bo")

        await room.intent(first, "grab", {"piece_id": "card-0"}, client_id="a")
        await room.intent(second, "grab", {"piece_id": "card-0"}, client_id="b")
        await room.settle()

        assert room.runtime.table.pieces["card-0"].held_by == SEAT_A
        assert second.socket.of_type("reject")[-1]["reason"] == (
            "Someone else is already holding that piece."
        )
        assert not first.socket.of_type("reject")


# -- drags: coalesced on the wire, written once to the log -----------------------------


async def test_a_drag_logs_only_the_position_the_piece_was_let_go_in() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")

        await room.intent(actor, "grab", {"piece_id": "card-0"})
        for step in range(20):
            await room.intent(
                actor,
                "move",
                {"piece_id": "card-0", "x": float(step), "y": 0.0},
            )
        await room.settle(0.2)
        await room.intent(actor, "release", {"piece_id": "card-0"})
        await room.settle()

        logged = [op for _seq, op in room.events()]
        assert logged.count("Move") == 1
        assert logged == ["Grab", "Move", "Release"]
        assert room.runtime.table.pieces["card-0"].x == 19.0


async def test_a_disconnect_releases_the_pieces_that_seat_was_holding() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        watcher = await room.connect(SEAT_B, display_name="Bo")

        await room.intent(actor, "grab", {"piece_id": "card-0"})
        await room.settle(0.1)
        await room.hub.detach(room.runtime, actor.connection, actor.writer)
        room.clients.remove(actor)
        await room.settle()

        assert room.runtime.table.pieces["card-0"].held_by is None
        notices = [message["text"] for message in watcher.socket.of_type("notice")]
        assert "Ana has left the table." in notices


# -- reconnect -------------------------------------------------------------------------


async def test_reconnect_with_a_small_gap_is_caught_up_with_patches() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        await room.intent(actor, "grab", {"piece_id": "card-0"})
        await room.settle(0.1)
        await room.intent(actor, "grab", {"piece_id": "card-1"})
        await room.settle(0.1)
        seq_before = room.runtime.seq

        actor.socket.clear()
        await room.hello(actor, last_seq=seq_before - 1)
        await room.settle()

        assert not actor.socket.of_type("snapshot")
        assert _patch_seqs(actor.socket) == [seq_before]


async def test_reconnect_with_too_large_a_gap_gets_a_fresh_snapshot() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        await room.intent(actor, "grab", {"piece_id": "card-0"})
        await room.settle(0.1)

        actor.socket.clear()
        await room.hello(actor, last_seq=0)
        await room.settle()

        assert len(actor.socket.of_type("snapshot")) == 1


async def test_a_first_hello_is_answered_with_a_snapshot_of_the_whole_table() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        await room.settle()

        snapshot = actor.socket.of_type("snapshot")[0]
        assert snapshot["you"]["seat_id"] == SEAT_A
        assert snapshot["view_table"]["version"] == room.runtime.table.version
        assert {seat["id"] for seat in snapshot["seats"]} == set(
            room.runtime.table.seats
        )


# -- backpressure ----------------------------------------------------------------------


async def test_a_client_that_stops_reading_is_resynchronised_not_backlogged() -> None:
    async with live_room() as room:
        slow = await room.connect(SEAT_B, display_name="Bo")
        actor = await room.connect(SEAT_A, display_name="Ana")
        await room.settle(0.1)

        slow.socket.blocked = True
        slow.socket.clear()
        for index in range(live.OUTBOUND_QUEUE_LIMIT + 40):
            await room.intent(
                actor, "point", {"x": float(index), "y": 0.0}, client_id="p"
            )
        await room.settle(0.4)

        assert slow.connection.queue.qsize() <= live.OUTBOUND_QUEUE_LIMIT
        slow.socket.unblock()
        await room.settle(0.2)
        assert slow.socket.of_type("snapshot")
        # The room itself kept working for everybody else.
        assert actor.socket.of_type("patches")


# -- the security boundary -------------------------------------------------------------


async def test_nothing_reaches_a_client_without_passing_through_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str | None] = []
    real_project = live.project

    def spy(table: Table, viewer_seat: str | None) -> Any:
        calls.append(viewer_seat)
        return real_project(table, viewer_seat)

    monkeypatch.setattr(live, "project", spy)

    async with live_room() as room:
        watcher = await room.connect(SEAT_B, display_name="Bo")
        await room.settle()

        assert calls == [SEAT_B]
        assert watcher.socket.of_type("snapshot")


async def test_another_seats_hand_never_carries_a_card_face() -> None:
    async with live_room() as room:
        watcher = await room.connect(SEAT_B, display_name="Bo")
        actor = await room.connect(SEAT_A, display_name="Ana")
        await room.settle(0.1)

        await room.intent(
            actor, "draw", {"count": 1, "from_zone": DECK, "to_zone": HAND_A}
        )
        await room.settle(0.1)
        card = next(
            piece.id
            for piece in room.runtime.table.pieces.values()
            if piece.zone_id == HAND_A
        )
        actor.socket.clear()
        watcher.socket.clear()
        await room.intent(actor, "flip", {"piece_id": card})
        await room.settle()

        # Ana turned her own card over, so she is told what it is.
        mine = [piece for piece in _pieces_in(actor.socket.sent) if piece["id"] == card]
        assert mine and all(piece["component_id"] for piece in mine)

        # Bo learns a card in Ana's hand changed, and nothing about its face.
        theirs = [
            piece for piece in _pieces_in(watcher.socket.sent) if piece["id"] == card
        ]
        assert theirs
        assert all(piece["component_id"] is None for piece in theirs)
        assert all(piece["face_up"] is False for piece in theirs)


async def test_a_peek_is_never_forwarded_to_anyone_else() -> None:
    async with live_room() as room:
        watcher = await room.connect(SEAT_B, display_name="Bo")
        actor = await room.connect(SEAT_A, display_name="Ana")
        await room.intent(
            actor, "draw", {"count": 1, "from_zone": DECK, "to_zone": HAND_A}
        )
        await room.settle(0.1)
        card = next(
            piece.id
            for piece in room.runtime.table.pieces.values()
            if piece.zone_id == HAND_A
        )
        await room.intent(actor, "flip", {"piece_id": card})
        await room.settle(0.1)
        watcher.socket.clear()
        actor.socket.clear()

        await room.intent(actor, "peek", {"piece_id": card})
        await room.settle()

        def peeks(socket: Any) -> list[dict[str, Any]]:
            return [
                patch
                for message in socket.of_type("patches")
                for patch in message["patches"]
                if patch["fields"].get("type") == "peek"
            ]

        assert peeks(actor.socket)
        assert not peeks(watcher.socket)


async def test_the_deck_face_is_hidden_from_everyone_including_the_drawer() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        await room.settle()

        deck_pieces = [
            piece
            for piece in _pieces_in(actor.socket.sent)
            if piece.get("zone_id") == DECK
        ]
        assert deck_pieces
        assert all(piece["component_id"] is None for piece in deck_pieces)


# -- presence and cursors --------------------------------------------------------------


async def test_cursors_go_out_as_presence_and_are_never_persisted() -> None:
    async with live_room() as room:
        watcher = await room.connect(SEAT_B, display_name="Bo")
        actor = await room.connect(SEAT_A, display_name="Ana")
        watcher.socket.clear()

        await room.send(actor, {"type": "cursor", "x": 12.0, "y": 34.0})
        await room.settle()

        presences = watcher.socket.of_type("presence")
        assert presences
        assert any(
            cursor == {"seat_id": SEAT_A, "x": 12.0, "y": 34.0}
            for message in presences
            for cursor in message["cursors"]
        )
        assert room.events() == []


async def test_a_heartbeat_changes_nothing() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        version = room.runtime.table.version

        await room.send(actor, {"type": "heartbeat"})
        await room.settle()

        assert room.runtime.table.version == version
        assert room.events() == []


# -- persistence -----------------------------------------------------------------------


async def test_a_macro_writes_a_snapshot_a_late_joiner_can_start_from() -> None:
    async with live_room() as room:
        facilitator = await room.connect(
            "facilitator", display_name="Facilitator", is_facilitator=True
        )

        await room.intent(
            facilitator,
            "move_to_zone",
            {"piece_id": "card-0", "zone_id": PUBLIC_TABLE},
        )
        await room.settle(0.1)
        await room.intent(facilitator, "reset_table", {})
        await room.settle()

        with session_scope(room.factory) as session:
            stored = session.get(TableState, room.runtime.room_id)
            assert stored is not None
            table = from_snapshot(stored.snapshot)

        assert table.pieces == {}


# -- the endpoint --------------------------------------------------------------


@pytest.fixture
def socket_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A TestClient whose pages and sockets share one in-memory database."""
    engine = make_test_engine()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_session() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(live.hub, "session_factory", factory)
    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app, follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_a_browser_that_has_not_joined_is_refused_the_socket(
    socket_client: TestClient,
) -> None:
    started = socket_client.post(
        "/start", data={"game_slug": "value-cards-trading", "display_name": "Ada"}
    )
    code = started.headers["location"].removeprefix("/t/")
    socket_client.cookies.clear()

    with socket_client.websocket_connect(f"/ws/t/{code}") as socket:
        assert socket.receive_json()["type"] == "notice"
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_the_facilitator_socket_answers_hello_with_a_snapshot(
    socket_client: TestClient,
) -> None:
    started = socket_client.post(
        "/start", data={"game_slug": "value-cards-trading", "display_name": "Ada"}
    )
    code = started.headers["location"].removeprefix("/t/")

    with socket_client.websocket_connect(f"/ws/t/{code}") as socket:
        socket.send_json({"type": "hello", "room_code": code, "last_seq": 0})
        message = socket.receive_json()

    assert message["type"] == "snapshot"
    assert message["you"]["display_name"] == "Ada"
    assert message["you"]["is_facilitator"] is True
