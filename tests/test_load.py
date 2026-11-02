"""A load check: eight people, 300 pieces, continuous activity.

Seats A and B drag cards around, two more take turns grabbing and flipping,
and the remaining people are observers. Memory must be flat and no
connection's outbound queue may back up. The run lasts
``SANDBOX_LOAD_SECONDS`` (default 8); CI's scheduled load job sets 600, the
ten minutes the build plan asks for.
"""

from __future__ import annotations

import asyncio
import gc
import os
import resource
import sys
import tracemalloc

from _live_support import Client, LiveFixture, live_room
from _model_support import SEAT_A, SEAT_B

SECONDS = float(os.environ.get("SANDBOX_LOAD_SECONDS", "8"))
PIECES = 300
OBSERVERS = 6


def _peak_rss_bytes() -> int:
    """Peak resident memory in bytes: macOS reports bytes, Linux kilobytes."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


async def _drag(room: LiveFixture, client: Client, first: int, stop: float) -> None:
    loop = asyncio.get_running_loop()
    step = 0
    while loop.time() < stop:
        piece = f"card-{first + step % 40}"
        await room.intent(client, "grab", {"piece_id": piece}, client_id=f"g{step}")
        for beat in range(6):
            await room.intent(
                client,
                "move",
                {"piece_id": piece, "x": float(beat * 9), "y": float(step % 50)},
                client_id=f"m{step}-{beat}",
            )
            await asyncio.sleep(0.02)
        await room.intent(client, "release", {"piece_id": piece}, client_id=f"r{step}")
        await room.intent(client, "flip", {"piece_id": piece}, client_id=f"f{step}")
        step += 1


async def test_eight_people_and_three_hundred_pieces_stay_flat_and_unbacklogged() -> (
    None
):
    async with live_room(deck_size=PIECES) as room:
        actors = [
            await room.connect(SEAT_A, display_name="Ana"),
            await room.connect(SEAT_B, display_name="Bo"),
        ]
        for n in range(OBSERVERS):
            await room.connect(None, display_name=f"Watcher {n}")
        assert len(room.clients) == 8
        assert len(room.runtime.table.pieces) == PIECES

        loop = asyncio.get_running_loop()
        tracemalloc.start()
        warm_until = loop.time() + min(5.0, SECONDS / 4)
        await asyncio.gather(
            _drag(room, actors[0], 0, warm_until),
            _drag(room, actors[1], 100, warm_until),
        )
        await room.settle(0.3)
        for client in room.clients:
            client.socket.clear()
        gc.collect()
        baseline, _ = tracemalloc.get_traced_memory()
        rss_before = _peak_rss_bytes()

        deepest = 0
        # Which connections were sent something during the run.
        served: set[int] = set()
        stop = loop.time() + SECONDS

        async def watch_queues() -> None:
            nonlocal deepest
            while loop.time() < stop:
                deepest = max(
                    deepest, *(c.connection.queue.qsize() for c in room.clients)
                )
                for number, client in enumerate(room.clients):
                    if client.socket.sent:
                        served.add(number)
                    # Stop the test log growing without bound: what matters is
                    # the server's memory, not the fake sockets'.
                    if len(client.socket.sent) > 500:
                        client.socket.clear()
                await asyncio.sleep(0.05)

        await asyncio.gather(
            _drag(room, actors[0], 0, stop),
            _drag(room, actors[1], 100, stop),
            watch_queues(),
        )
        await room.settle(0.5)
        # What the fake sockets kept is the test's, not the server's: drop it
        # before measuring, as it was dropped before the baseline.
        for client in room.clients:
            client.socket.clear()
        gc.collect()
        current, _ = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_after = _peak_rss_bytes()

        # No backlog: queues drained and never near their limit.
        assert all(c.connection.queue.qsize() == 0 for c in room.clients)
        assert deepest < 60, f"an outbound queue reached {deepest} messages"
        # Flat memory: what the room holds does not grow with time.
        grown = current - baseline
        assert grown < 8 * 1024 * 1024, f"traced memory grew by {grown} bytes"
        rss_grown = rss_after - rss_before
        assert rss_grown < 150 * 1024 * 1024, (
            f"peak resident memory grew by {rss_grown} bytes"
        )
        # Everyone was still being served at the end.
        assert served == set(range(len(room.clients)))
