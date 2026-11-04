"""The Pieces menu: every room adds dice and player pieces where someone looks."""

from __future__ import annotations

from typing import Any

from test_live_classes import open_room


def _menu(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    menu: list[dict[str, Any]] = snapshot["pieces_menu"]
    return menu


async def test_the_menu_lists_the_die_and_each_colour_of_player_piece() -> None:
    async with open_room(0) as (room, host, _guests):
        await room.settle(0.05)
        menu = _menu(host.socket.of_type("snapshot")[-1])
        ids = [entry["component_id"] for entry in menu]
        assert ids[0] == "d6"
        assert {
            f"{kind}-{n}" for kind in ("cube", "meeple", "token") for n in range(1, 7)
        } <= set(ids)
        tints = {e["tint_index"] for e in menu if e["kind"] == "token"}
        assert tints == set(range(6))


async def test_adding_a_piece_puts_it_where_it_was_asked_for() -> None:
    async with open_room(0) as (room, host, _guests):
        before = set(room.runtime.table.pieces)
        await room.intent(
            host,
            "add_piece",
            {"component_id": "token-2", "x": 600, "y": 500},
            client_id="a",
        )
        await room.settle(0.05)
        (added,) = set(room.runtime.table.pieces) - before
        piece = room.runtime.table.pieces[added]
        assert piece.component_id == "token-2"
        assert (piece.x, piece.y) == (600, 500)
        assert host.socket.of_type("ack")[-1]["client_id"] == "a"


async def test_only_the_menus_own_pieces_can_be_added() -> None:
    async with open_room(0) as (room, host, _guests):
        before = set(room.runtime.table.pieces)
        for component in ("pairs:ace-of-hearts", "note", "nothing"):
            await room.intent(
                host,
                "add_piece",
                {"component_id": component, "x": 1, "y": 1},
                client_id=component,
            )
        await room.settle(0.05)
        assert set(room.runtime.table.pieces) == before
        assert len(host.socket.of_type("reject")) == 3
