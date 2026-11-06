"""A still picture of an exercise's table just after setup.

The picture is drawn from ``project(table, None)`` - what a spectator with
no seat may see - so a preview can show nothing that is not public: a deck
is a stack of backs, a hand is an outline. The table is built exactly as a
new room's would be, with every seat the exercise allows taken, so each
seat's own zones appear.

It is an inline SVG laid out here and drawn by ``_table_preview.html``, so
its colours come from the design tokens like everything else.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sandbox.games import Game
from sandbox.games.engine import build_seat, build_table
from sandbox.games.loader import Face
from sandbox.model import Ok, Polygon, Rect, Table, TableRng, project, run_op

# The table client's default piece sizes (``client/src/piece-node.ts``), so a
# preview's cards are the same shape as the real table's.
DEFAULT_SIZES: dict[str, tuple[float, float]] = {
    "card": (208, 288),
    "die": (72, 72),
    "cube": (56, 56),
    "meeple": (64, 60),
    "token": (64, 64),
    "note": (160, 128),
    "marker": (36, 36),
    "board": (480, 320),
    "tile": (300, 400),
}
MARGIN = 40.0
PREVIEW_SEED = 0


@dataclass(frozen=True)
class PreviewZone:
    x: float
    y: float
    width: float
    height: float
    label: str
    visibility: str
    kind: str


@dataclass(frozen=True)
class PreviewPiece:
    x: float
    y: float
    width: float
    height: float
    rotation: float
    kind: str
    title: str | None


@dataclass(frozen=True)
class Preview:
    """Everything the template needs to draw one table."""

    title: str
    view_box: str
    zones: tuple[PreviewZone, ...]
    pieces: tuple[PreviewPiece, ...]
    seats: int


def _set_up(game: Game) -> Table:
    table = Table(rng=TableRng(seed=PREVIEW_SEED))
    seat_id, transaction = build_table(game, table, participant_id=None)
    if not isinstance(run_op(table, seat_id, transaction), Ok):
        raise RuntimeError(f"{game.slug}'s table could not be set up.")
    for _ in range(game.definition.meta.players.max - 1):
        seat_id, transaction = build_seat(game, table, participant_id=None)
        if not isinstance(run_op(table, seat_id, transaction), Ok):
            raise RuntimeError(f"{game.slug} could not seat another person.")
    return table


def table_preview(game: Game) -> Preview:
    """The table for ``game`` after setup, as a spectator sees it."""
    return table_picture(_set_up(game), game.faces(), game.title)


def table_picture(
    table: Table,
    faces: Mapping[str, Face],
    title: str,
    *,
    all_faces: bool = False,
) -> Preview:
    """``table`` drawn as a spectator sees it, or with every face showing.

    ``all_faces`` is for the facilitator's replay: a face-down card is drawn
    with its title. Without it, nothing is drawn that is not public.
    """
    view = project(table, None)
    raw = table.pieces

    zones: list[PreviewZone] = []
    for zone in view.zones:
        if isinstance(zone.geometry, Rect):
            box = zone.geometry
            x, y, width, height = box.x, box.y, box.width, box.height
        else:
            assert isinstance(zone.geometry, Polygon)
            xs = [point[0] for point in zone.geometry.points] or [0.0]
            ys = [point[1] for point in zone.geometry.points] or [0.0]
            x, y = min(xs), min(ys)
            width, height = max(xs) - x, max(ys) - y
        zones.append(
            PreviewZone(
                x=x,
                y=y,
                width=width,
                height=height,
                label=zone.label,
                visibility=str(zone.visibility),
                kind=str(zone.kind),
            )
        )

    pieces: list[PreviewPiece] = []
    zone_order = {zone.id: index for index, zone in enumerate(view.zones)}
    for piece in sorted(view.pieces, key=lambda p: (zone_order.get(p.zone_id, 0), p.z)):
        component = (
            raw[piece.id].component_id
            if all_faces and piece.id in raw
            else piece.component_id
        )
        face = None if component is None else faces.get(component)
        width, height = DEFAULT_SIZES.get(str(piece.kind), DEFAULT_SIZES["token"])
        if face is not None:
            width = face.width or width
            height = face.height or height
        pieces.append(
            PreviewPiece(
                x=piece.x - width / 2,
                y=piece.y - height / 2,
                width=width,
                height=height,
                rotation=piece.rotation,
                kind=str(piece.kind),
                title=None if face is None else face.title,
            )
        )

    lefts = [zone.x for zone in zones] + [piece.x for piece in pieces] or [0.0]
    tops = [zone.y for zone in zones] + [piece.y for piece in pieces] or [0.0]
    rights = [zone.x + zone.width for zone in zones] + [
        piece.x + piece.width for piece in pieces
    ] or [0.0]
    bottoms = [zone.y + zone.height for zone in zones] + [
        piece.y + piece.height for piece in pieces
    ] or [0.0]
    left, top = min(lefts) - MARGIN, min(tops) - MARGIN
    width, height = max(rights) - left + MARGIN, max(bottoms) - top + MARGIN
    return Preview(
        title=title,
        view_box=f"{left:g} {top:g} {width:g} {height:g}",
        zones=tuple(zones),
        pieces=tuple(pieces),
        seats=len(view.seats),
    )


__all__ = ["Preview", "PreviewPiece", "PreviewZone", "table_picture", "table_preview"]
