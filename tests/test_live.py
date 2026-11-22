"""The realtime layer: ordering, reconnect, rejection, backpressure, and the
one rule that matters most - nothing leaves the server unprojected.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from _db_support import make_test_engine
from _live_support import FakeSocket, live_room
from _model_support import (
    DECK,
    DISCARD,
    FACILITATOR,
    HAND_A,
    HAND_B,
    PUBLIC_TABLE,
    SEAT_A,
    SEAT_B,
)
from _room_support import start_room
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from starlette.websockets import WebSocketDisconnect

from sandbox.db.engine import session_scope
from sandbox.db.models import TableState
from sandbox.db.snapshot import from_snapshot
from sandbox.model import Move, MoveToZone, Table
from sandbox.web import live
from sandbox.web.app import app, get_session
from sandbox.web.live import HelloMessage


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
    assert len(live.OPERATIONS) == 36


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


async def test_a_disconnect_releases_the_pieces_after_the_grace_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live, "LEAVE_GRACE_SECONDS", 0.3)
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        watcher = await room.connect(SEAT_B, display_name="Bo")

        await room.intent(actor, "grab", {"piece_id": "card-0"})
        await room.settle(0.1)
        await room.hub.detach(room.runtime, actor.connection, actor.writer)
        room.clients.remove(actor)
        await room.settle(0.1)

        assert room.runtime.table.pieces["card-0"].held_by == SEAT_A
        await room.settle(0.5)
        assert room.runtime.table.pieces["card-0"].held_by is None
        notices = [message["text"] for message in watcher.socket.of_type("notice")]
        assert "Ana has left the table." in notices


async def test_reconnecting_within_the_grace_period_keeps_the_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live, "LEAVE_GRACE_SECONDS", 0.4)
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        # Someone stays, so the room is still live while Ana is away.
        await room.connect(SEAT_B, display_name="Bo")
        await room.intent(actor, "grab", {"piece_id": "card-0"})
        await room.settle(0.1)
        await room.hub.detach(room.runtime, actor.connection, actor.writer)
        room.clients.remove(actor)
        await room.settle(0.1)

        await room.connect(SEAT_A, display_name="Ana")
        await room.settle(0.6)

        assert room.runtime.table.pieces["card-0"].held_by == SEAT_A


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


async def test_a_new_socket_from_the_same_run_is_caught_up_by_replay() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        watcher = await room.connect(SEAT_B, display_name="Bo")
        await room.intent(actor, "grab", {"piece_id": "card-0"})
        await room.settle(0.1)
        epoch = room.runtime.epoch
        seen = room.runtime.seq
        await room.intent(actor, "release", {"piece_id": "card-0"})
        await room.settle(0.1)
        await room.hub.detach(room.runtime, actor.connection, actor.writer)
        room.clients.remove(actor)
        watcher.socket.clear()

        # A brand new connection (a phone that woke up) says how far it got.
        returning = await room.connect(
            SEAT_A, display_name="Ana", last_seq=seen, epoch=epoch
        )
        await room.settle()

        assert not returning.socket.of_type("snapshot")[1:]
        assert _patch_seqs(returning.socket) == list(
            range(seen + 1, room.runtime.seq + 1)
        )


async def test_a_seq_from_another_run_of_the_room_gets_a_snapshot() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        await room.intent(actor, "grab", {"piece_id": "card-0"})
        await room.settle(0.1)
        seen = room.runtime.seq

        stale = await room.connect(
            SEAT_B, display_name="Bo", last_seq=seen, epoch="an-earlier-run"
        )
        await room.settle()

        assert len(stale.socket.of_type("snapshot")) == 1
        assert not stale.socket.of_type("patches")


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


# -- interaction: menus, acknowledgements, reveals ------------------------------------


async def _card_in_hand_a(room: Any, actor: Any) -> str:
    await room.intent(actor, "draw", {"count": 1, "from_zone": DECK, "to_zone": HAND_A})
    await room.settle(0.1)
    card: str = next(
        piece.id
        for piece in room.runtime.table.pieces.values()
        if piece.zone_id == HAND_A
    )
    await room.intent(actor, "flip", {"piece_id": card})
    await room.settle(0.1)
    return card


def _faces_described(socket: Any) -> set[str]:
    return {
        component["id"]
        for message in socket.sent
        if message["type"] in ("snapshot", "patches")
        for component in message.get("components", [])
    }


async def test_a_menu_lists_what_the_model_allows_with_peoples_names() -> None:
    async with live_room() as room:
        await room.connect(SEAT_B, display_name="Bo")
        actor = await room.connect(SEAT_A, display_name="Ana")
        card = await _card_in_hand_a(room, actor)
        actor.socket.clear()

        await room.send(
            actor, {"type": "menu_request", "client_id": "m1", "piece_id": card}
        )
        await room.settle(0.1)

        menu = actor.socket.of_type("menu")[-1]
        assert menu["client_id"] == "m1"
        assert menu["piece_id"] == card
        items = {item["id"]: item for item in menu["items"]}
        assert items[f"show_to:{SEAT_B}"]["label"] == "Bo"
        # Someone else's hand is named for them, not for their seat.
        assert items[f"move:{HAND_B}"]["label"] == "Bo's hand"
        assert items[f"show_to:{SEAT_B}"]["group"] == "Show to…"
        assert items[f"show_to:{SEAT_B}"]["op_type"] == "show_to"
        assert items[f"show_to:{SEAT_B}"]["payload"] == {
            "piece_id": card,
            "seat_ids": [SEAT_B],
        }
        assert "delete" not in items


async def test_a_menu_item_sent_back_as_an_intent_does_what_it_says() -> None:
    async with live_room() as room:
        watcher = await room.connect(SEAT_B, display_name="Bo")
        actor = await room.connect(SEAT_A, display_name="Ana")
        card = await _card_in_hand_a(room, actor)
        await room.send(
            actor, {"type": "menu_request", "client_id": "m1", "piece_id": card}
        )
        await room.settle(0.1)
        item = next(
            item
            for item in actor.socket.of_type("menu")[-1]["items"]
            if item["id"] == f"show_to:{SEAT_B}"
        )

        await room.intent(actor, item["op_type"], item["payload"])
        await room.settle(0.1)

        assert room.runtime.table.pieces[card].revealed_to == frozenset({SEAT_B})
        shown = [p for p in _pieces_in(watcher.socket.sent) if p["id"] == card]
        assert shown[-1]["component_id"] is not None


async def test_an_observer_is_offered_nothing() -> None:
    async with live_room() as room:
        observer = await room.connect(None, display_name="Visitor")

        await room.send(
            observer,
            {"type": "menu_request", "client_id": "m1", "piece_id": "card-0"},
        )
        await room.settle(0.1)

        assert observer.socket.of_type("menu")[-1]["items"] == []


async def test_an_accepted_intent_is_acknowledged_after_its_patches() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        actor.socket.clear()

        await room.intent(
            actor,
            "move_to_zone",
            {"piece_id": "card-0", "zone_id": PUBLIC_TABLE},
            client_id="i-7",
        )
        await room.settle(0.1)

        kinds = [message["type"] for message in actor.socket.sent]
        assert "patches" in kinds
        acks = [m for m in actor.socket.sent if m["type"] == "ack"]
        assert acks == [{"type": "ack", "client_id": "i-7"}]
        assert kinds.index("patches") < kinds.index("ack")


async def test_a_rejected_intent_is_not_acknowledged() -> None:
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")

        await room.intent(actor, "reset_table", {}, client_id="i-8")
        await room.settle(0.1)

        assert actor.socket.of_type("ack") == []
        assert actor.socket.of_type("reject")[-1]["client_id"] == "i-8"


async def test_a_newly_visible_face_is_described_to_its_viewer_only() -> None:
    async with live_room() as room:
        room.runtime.components = {
            f"the-{index}-of-values": live.ComponentView(
                id=f"the-{index}-of-values", title=f"Value {index}"
            )
            for index in range(6)
        }
        watcher = await room.connect(SEAT_B, display_name="Bo")
        actor = await room.connect(SEAT_A, display_name="Ana")
        # Nothing on the table is face-up yet, so the snapshot describes nothing.
        assert _faces_described(actor.socket) == set()

        card = await _card_in_hand_a(room, actor)
        component = room.runtime.table.pieces[card].component_id

        assert _faces_described(actor.socket) == {component}
        assert _faces_described(watcher.socket) == set()

        await room.intent(actor, "show_to", {"piece_id": card, "seat_ids": [SEAT_B]})
        await room.settle(0.1)

        assert _faces_described(watcher.socket) == {component}


async def test_a_face_is_described_only_once_per_connection() -> None:
    async with live_room() as room:
        room.runtime.components = {
            f"the-{index}-of-values": live.ComponentView(id=f"the-{index}-of-values")
            for index in range(6)
        }
        actor = await room.connect(SEAT_A, display_name="Ana")
        card = await _card_in_hand_a(room, actor)
        actor.socket.clear()

        await room.intent(actor, "rotate", {"piece_id": card})
        await room.settle(0.1)

        assert actor.socket.of_type("patches")
        assert _faces_described(actor.socket) == set()


async def test_leaving_the_table_puts_away_a_card_being_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live, "LEAVE_GRACE_SECONDS", 0.2)
    async with live_room() as room:
        watcher = await room.connect(SEAT_B, display_name="Bo")
        actor = await room.connect(SEAT_A, display_name="Ana")
        card = await _card_in_hand_a(room, actor)
        await room.intent(actor, "show_to", {"piece_id": card})
        await room.settle(0.1)
        watcher.socket.clear()

        room.clients.remove(actor)
        await room.hub.detach(room.runtime, actor.connection, actor.writer)
        await room.settle(0.5)

        assert room.runtime.table.pieces[card].revealed_to == frozenset()
        ended = [
            patch["fields"]
            for message in watcher.socket.of_type("patches")
            for patch in message["patches"]
            if patch["fields"].get("type") == "show_end"
        ]
        assert ended == [{"type": "show_end", "piece_id": card, "by_seat": SEAT_A}]
        theirs = [p for p in _pieces_in(watcher.socket.sent) if p["id"] == card]
        assert theirs[-1]["component_id"] is None


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
    started = start_room(
        socket_client,
        data={
            "display_name": "Ada",
            "as_facilitator": "true",
        },
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
    started = start_room(
        socket_client,
        data={
            "display_name": "Ada",
            "as_facilitator": "true",
        },
    )
    code = started.headers["location"].removeprefix("/t/")

    with socket_client.websocket_connect(f"/ws/t/{code}") as socket:
        socket.send_json({"type": "hello", "room_code": code, "last_seq": 0})
        message = socket.receive_json()

    assert message["type"] == "snapshot"
    assert message["you"]["display_name"] == "Ada"
    assert message["you"]["is_facilitator"] is True


# -- the facilitator taking a piece mid-drag -------------------------------------------


async def test_the_facilitator_can_take_a_piece_out_of_someones_drag() -> None:
    async with live_room() as room:
        ana = await room.connect(SEAT_A, display_name="Ana")
        host = await room.connect(FACILITATOR, display_name="Ines", is_facilitator=True)
        await room.intent(ana, "grab", {"piece_id": "card-0"}, client_id="g")
        await room.intent(
            ana, "move", {"piece_id": "card-0", "x": 40, "y": 50}, client_id="m1"
        )
        await room.settle(0.1)

        await room.intent(
            host,
            "move_to_zone",
            {"piece_id": "card-0", "zone_id": DISCARD},
            client_id="t",
        )
        await room.intent(
            ana, "move", {"piece_id": "card-0", "x": 90, "y": 90}, client_id="m2"
        )
        await room.settle()

        piece = room.runtime.table.pieces["card-0"]
        assert piece.zone_id == DISCARD
        assert piece.held_by is None
        assert ana.socket.of_type("reject")[-1] == {
            "type": "reject",
            "client_id": "m2",
            "reason": "The facilitator took that piece.",
        }
        # Ana's drag up to the take is logged before the take itself.
        assert [op for _seq, op in room.events()] == ["Grab", "Move", "MoveToZone"]


async def test_after_a_take_the_same_person_may_pick_the_piece_up_again() -> None:
    async with live_room() as room:
        ana = await room.connect(SEAT_A, display_name="Ana")
        host = await room.connect(FACILITATOR, display_name="Ines", is_facilitator=True)
        await room.intent(ana, "grab", {"piece_id": "card-0"}, client_id="g1")
        await room.intent(
            host,
            "move_to_zone",
            {"piece_id": "card-0", "zone_id": DISCARD},
            client_id="t",
        )
        await room.intent(ana, "grab", {"piece_id": "card-0"}, client_id="g2")
        await room.settle()

        assert room.runtime.table.pieces["card-0"].held_by == SEAT_A
        assert not [r for r in ana.socket.of_type("reject") if r["client_id"] == "g2"]


async def test_a_server_restart_restores_the_table_and_sends_clients_a_snapshot() -> (
    None
):
    async with live_room() as room:
        actor = await room.connect(SEAT_A, display_name="Ana")
        await room.intent(actor, "grab", {"piece_id": "card-0"})
        await room.intent(actor, "move", {"piece_id": "card-0", "x": 123.0, "y": 45.0})
        await room.intent(actor, "release", {"piece_id": "card-0"})
        await room.settle(0.3)
        epoch = room.runtime.epoch
        seen = room.runtime.seq
        code = room.runtime.code
        await room.hub.shutdown()

        # The server is started again: a new hub reads the table from its snapshot.
        restarted = live.LiveHub(session_factory=room.factory)
        try:
            runtime = await restarted.runtime_for(code)
            assert runtime is not None
            piece = runtime.table.pieces["card-0"]
            assert (piece.x, piece.y) == (123.0, 45.0)
            assert runtime.epoch != epoch

            socket = FakeSocket()
            connection, writer = await restarted.attach(
                runtime,
                socket,
                participant_id=f"participant-{SEAT_A}",
                display_name="Ana",
                seat_id=SEAT_A,
                is_facilitator=False,
                is_observer=False,
            )
            # The browser reconnects with the seq and epoch it last saw.
            await runtime.submit(
                connection,
                HelloMessage(room_code=code, last_seq=seen, epoch=epoch),
            )
            await runtime.drain()
            assert len(socket.of_type("snapshot")) == 1
            await restarted.detach(runtime, connection, writer)
        finally:
            await restarted.shutdown()
