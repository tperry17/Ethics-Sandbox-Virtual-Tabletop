"""Round-trip a ``sandbox.model`` ``Table`` to and from a JSON-safe dict.

This is the only place that knows both the pure domain model and what a JSON
column can hold. Nothing here changes what a table means - it only changes
how one is written down, so ``from_snapshot(to_snapshot(table))`` always
reproduces the original, including its remaining randomness.
"""

from __future__ import annotations

from typing import Any

from sandbox.model import (
    Layout,
    Piece,
    PieceKind,
    Polygon,
    Rect,
    Seat,
    Stroke,
    Table,
    TableRng,
    Visibility,
    Zone,
    ZoneKind,
)
from sandbox.model.entities import Geometry

Snapshot = dict[str, Any]


def to_snapshot(table: Table) -> Snapshot:
    """A JSON-safe dict capturing everything needed to reconstruct ``table``."""
    return {
        "pieces": {
            piece_id: _dump_piece(piece) for piece_id, piece in table.pieces.items()
        },
        "zones": {zone_id: _dump_zone(zone) for zone_id, zone in table.zones.items()},
        "seats": {seat_id: _dump_seat(seat) for seat_id, seat in table.seats.items()},
        "strokes": {
            stroke_id: _dump_stroke(stroke)
            for stroke_id, stroke in table.strokes.items()
        },
        "rng": _dump_rng(table.rng),
        "version": table.version,
        "applied_op_ids": sorted(table.applied_op_ids),
    }


def from_snapshot(data: Snapshot) -> Table:
    """The ``Table`` that ``data`` describes."""
    return Table(
        pieces={
            piece_id: _load_piece(piece_id, fields)
            for piece_id, fields in data["pieces"].items()
        },
        zones={
            zone_id: _load_zone(zone_id, fields)
            for zone_id, fields in data["zones"].items()
        },
        seats={
            seat_id: _load_seat(seat_id, fields)
            for seat_id, fields in data["seats"].items()
        },
        strokes={
            stroke_id: _load_stroke(stroke_id, fields)
            for stroke_id, fields in data["strokes"].items()
        },
        rng=_load_rng(data["rng"]),
        version=data["version"],
        applied_op_ids=set(data["applied_op_ids"]),
    )


# -- pieces -------------------------------------------------------------------


def _dump_piece(piece: Piece) -> Snapshot:
    return {
        "kind": piece.kind.value,
        "component_id": piece.component_id,
        "zone_id": piece.zone_id,
        "x": piece.x,
        "y": piece.y,
        "z": piece.z,
        "rotation": piece.rotation,
        "face_up": piece.face_up,
        "held_by": piece.held_by,
        "locked": piece.locked,
        "revealed_to": sorted(piece.revealed_to),
        "group_id": piece.group_id,
        "props": piece.props,
    }


def _load_piece(piece_id: str, fields: Snapshot) -> Piece:
    return Piece(
        id=piece_id,
        kind=PieceKind(fields["kind"]),
        component_id=fields["component_id"],
        zone_id=fields["zone_id"],
        x=fields["x"],
        y=fields["y"],
        z=fields["z"],
        rotation=fields["rotation"],
        face_up=fields["face_up"],
        held_by=fields["held_by"],
        locked=fields["locked"],
        revealed_to=frozenset(fields["revealed_to"]),
        group_id=fields["group_id"],
        props=dict(fields["props"]),
    )


# -- zones ----------------------------------------------------------------


def _dump_geometry(geometry: Geometry) -> Snapshot:
    if isinstance(geometry, Rect):
        return {
            "shape": "rect",
            "x": geometry.x,
            "y": geometry.y,
            "width": geometry.width,
            "height": geometry.height,
        }
    return {"shape": "polygon", "points": [list(point) for point in geometry.points]}


def _load_geometry(fields: Snapshot) -> Geometry:
    if fields["shape"] == "rect":
        return Rect(
            x=fields["x"], y=fields["y"], width=fields["width"], height=fields["height"]
        )
    points = tuple((point[0], point[1]) for point in fields["points"])
    return Polygon(points=points)


def _dump_zone(zone: Zone) -> Snapshot:
    return {
        "kind": zone.kind.value,
        "label": zone.label,
        "geometry": _dump_geometry(zone.geometry),
        "visibility": zone.visibility.value,
        "layout": zone.layout.value,
        "owner_seat": zone.owner_seat,
        "capacity": zone.capacity,
    }


def _load_zone(zone_id: str, fields: Snapshot) -> Zone:
    return Zone(
        id=zone_id,
        kind=ZoneKind(fields["kind"]),
        label=fields["label"],
        geometry=_load_geometry(fields["geometry"]),
        visibility=Visibility(fields["visibility"]),
        layout=Layout(fields["layout"]),
        owner_seat=fields["owner_seat"],
        capacity=fields["capacity"],
    )


# -- seats ------------------------------------------------------------------


def _dump_seat(seat: Seat) -> Snapshot:
    return {
        "label": seat.label,
        "tint_index": seat.tint_index,
        "participant_id": seat.participant_id,
        "is_facilitator": seat.is_facilitator,
    }


def _load_seat(seat_id: str, fields: Snapshot) -> Seat:
    return Seat(
        id=seat_id,
        label=fields["label"],
        tint_index=fields["tint_index"],
        participant_id=fields["participant_id"],
        is_facilitator=fields["is_facilitator"],
    )


# -- strokes ------------------------------------------------------------------


def _dump_stroke(stroke: Stroke) -> Snapshot:
    return {
        "seat_id": stroke.seat_id,
        "colour": stroke.colour,
        "width": stroke.width,
        "points": [list(point) for point in stroke.points],
        "created_at": stroke.created_at,
        "closed": stroke.closed,
    }


def _load_stroke(stroke_id: str, fields: Snapshot) -> Stroke:
    return Stroke(
        id=stroke_id,
        seat_id=fields["seat_id"],
        colour=fields["colour"],
        width=fields["width"],
        points=[(point[0], point[1]) for point in fields["points"]],
        created_at=fields["created_at"],
        closed=fields["closed"],
    )


# -- rng ------------------------------------------------------------------


def _dump_rng(rng: TableRng) -> Snapshot:
    version, internal_state, gauss_next = rng.get_state()
    return {"seed": rng.seed, "state": [version, list(internal_state), gauss_next]}


def _load_rng(fields: Snapshot) -> TableRng:
    version, internal_state, gauss_next = fields["state"]
    rng = TableRng(seed=fields["seed"])
    rng.set_state((version, tuple(internal_state), gauss_next))
    return rng
