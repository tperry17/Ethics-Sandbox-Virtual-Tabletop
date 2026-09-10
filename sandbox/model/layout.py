"""Automatic placement of pieces within a zone, per the zone's layout rule.

Positions are computed here, in the model, rather than by the table client -
"Python owns everything that counts" includes where a piece lands when it is
dealt, drawn, or spawned without an explicit position.
"""

from __future__ import annotations

import math

from sandbox.model.entities import Polygon, Rect, Zone
from sandbox.model.types import Layout


def _rect_centre(rect: Rect) -> tuple[float, float]:
    return (rect.x + rect.width / 2, rect.y + rect.height / 2)


def _polygon_centre(polygon: Polygon) -> tuple[float, float]:
    if not polygon.points:
        return (0.0, 0.0)
    xs = [x for x, _ in polygon.points]
    ys = [y for _, y in polygon.points]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def place_in_zone(zone: Zone, index: int, count: int) -> tuple[float, float, float]:
    """Where the piece at ``index`` of ``count`` should sit, and its rotation.

    A stack keeps every piece at one point, distinguished only by z-order. A
    fan spreads pieces across the zone's width with a small rotation each,
    like cards held in a hand. A spread lays pieces out flat in a row. A grid
    tiles them in rows and columns. ``free`` layout, and polygon-shaped
    zones (whose outline this function does not otherwise reason about),
    return the zone's centre - callers that want a specific spot should pass
    their own x/y rather than relying on automatic placement.
    """
    if isinstance(zone.geometry, Polygon):
        x, y = _polygon_centre(zone.geometry)
        return (x, y, 0.0)

    rect = zone.geometry
    count = max(count, 1)
    index = min(max(index, 0), count - 1)

    if zone.layout is Layout.FAN:
        span = min(count - 1, 8) * 6.0
        x = rect.x + rect.width * (index + 0.5) / count
        y = rect.y + rect.height / 2
        rotation = 0.0 if count == 1 else -span / 2 + span * index / (count - 1)
        return (x, y, rotation)

    if zone.layout is Layout.SPREAD:
        x = rect.x + rect.width * (index + 0.5) / count
        y = rect.y + rect.height / 2
        return (x, y, 0.0)

    if zone.layout is Layout.GRID:
        columns = max(1, math.ceil(math.sqrt(count)))
        rows = math.ceil(count / columns)
        row, col = divmod(index, columns)
        cell_width = rect.width / columns
        cell_height = rect.height / max(rows, 1)
        x = rect.x + cell_width * (col + 0.5)
        y = rect.y + cell_height * (row + 0.5)
        return (x, y, 0.0)

    # STACK and FREE both default to the zone's centre; a stack distinguishes
    # its pieces by z-order alone, and free-form placement waits for an
    # explicit position from whoever moved the piece there.
    x, y = _rect_centre(rect)
    return (x, y, 0.0)
