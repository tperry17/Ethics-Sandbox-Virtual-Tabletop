"""No message reaches a client carrying a face it is not entitled to see.

A session of each exercise is played through the live hub: a class is
started, its people are seated and sorted, the buttons are pressed, and
every seat turns over, moves and shows cards. After each step the test
records which component ids each seat's projection of the table entitles it
to. At the end, every component id found anywhere in anything that seat was
sent must be one it was entitled to at some point, and nothing else may appear.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from test_live_classes import _act, open_room

from sandbox.model import project

EXERCISES = [
    ("value-cards-room", "value-cards-trading", 3),
    ("democracy-room", "scenario-1", 9),
]


def _ids_in(value: Any, known: set[str]) -> set[str]:
    """Every known component id that appears anywhere in ``value``."""
    text = json.dumps(value)
    return {component for component in known if f'"{component}"' in text}


def _entitled(room: Any, seat_id: str | None) -> set[str]:
    view = project(room.runtime.table, seat_id)
    return {piece.component_id for piece in view.pieces if piece.component_id}


@pytest.mark.parametrize(("kind", "slug", "people"), EXERCISES)
async def test_no_message_carries_a_face_its_recipient_may_not_see(
    kind: str, slug: str, people: int
) -> None:
    async with open_room(people, kind) as (room, host, guests):
        everyone = [host, *guests]
        entitled: dict[str, set[str]] = {c.seat_id or "": set() for c in everyone}
        every_component: set[str] = set()

        def sample() -> None:
            table = room.runtime.table
            every_component.update(
                p.component_id for p in table.pieces.values() if p.component_id
            )
            for client in everyone:
                entitled[client.seat_id or ""] |= _entitled(room, client.seat_id)

        await _act(room, host, {"action": "start", "slug": slug, "tables": 1}, "start")
        class_id = next(iter(room.runtime.table.classes))
        await _act(room, host, {"action": "sort_preview", "class_id": class_id})
        (proposal,) = host.socket.of_type("class_sort")
        await _act(
            room,
            host,
            {"action": "assign", "class_id": class_id, "tables": proposal["tables"]},
        )
        await _act(room, host, {"action": "begin", "class_id": class_id})
        sample()

        table_id = next(iter(room.runtime.table.activities))
        macros = [m["id"] for m in host.socket.of_type("snapshot")[-1]["macros"]]
        for macro_id in ("deal", "shuffle"):
            if macro_id in macros:
                await room.intent(
                    host,
                    "macro",
                    {"macro_id": macro_id, "activity_id": table_id},
                    client_id=f"m-{macro_id}",
                )
                await room.settle(0.1)
                sample()

        # Everyone turns over, picks up and moves what they can reach.
        for number, client in enumerate(guests):
            view = project(room.runtime.table, client.seat_id)
            for piece in view.pieces[:12]:
                for op, payload in (
                    ("flip", {"piece_id": piece.id}),
                    ("move", {"piece_id": piece.id, "x": 40.0 + number, "y": 40.0}),
                ):
                    await room.intent(
                        client, op, payload, client_id=f"{op}-{number}-{piece.id}"
                    )
                await room.settle(0.02)
                sample()
        await room.settle(0.3)
        sample()

        assert every_component, "the exercise produced no cards to check"
        for client in everyone:
            seen = set()
            for message in client.socket.sent:
                seen |= _ids_in(message, every_component)
            allowed = entitled[client.seat_id or ""]
            assert seen <= allowed, (
                f"{client.seat_id} was sent faces it was never entitled to: "
                f"{sorted(seen - allowed)[:5]}"
            )
        # The check has teeth: cards were dealt to people.
        assert any(entitled[c.seat_id or ""] for c in guests)
