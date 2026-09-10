"""Round-tripping a Table through the JSON snapshot format."""

from __future__ import annotations

from _model_support import DECK, PUBLIC_TABLE, SEAT_A, build_sample_table

from sandbox.db.snapshot import from_snapshot, to_snapshot
from sandbox.model import Grab, Move, Ok, Shuffle, Stroke, Table, run_op


def test_empty_table_round_trips() -> None:
    table = Table()

    restored = from_snapshot(to_snapshot(table))

    assert to_snapshot(restored) == to_snapshot(table)


def test_populated_table_round_trips_exactly() -> None:
    table = build_sample_table(seed=7)

    restored = from_snapshot(to_snapshot(table))

    assert to_snapshot(restored) == to_snapshot(table)
    assert restored.version == table.version
    assert restored.rng.get_state() == table.rng.get_state()
    assert restored.rng.seed == table.rng.seed


def test_round_trip_preserves_advanced_rng_state() -> None:
    table = build_sample_table(seed=42)
    outcome = run_op(table, SEAT_A, Shuffle(zone_id=DECK))
    assert isinstance(outcome, Ok)

    restored = from_snapshot(to_snapshot(table))

    assert restored.rng.get_state() == table.rng.get_state()
    # The restored RNG must continue exactly where the original would.
    assert restored.rng.shuffled_indices(6) == table.rng.clone().shuffled_indices(6)


def test_round_trip_preserves_held_and_revealed_pieces() -> None:
    table = build_sample_table()
    run_op(table, SEAT_A, Grab(piece_id="card-0"))
    run_op(table, SEAT_A, Move(piece_id="card-0", x=12.0, y=34.0))
    piece = table.pieces["card-0"]
    piece.revealed_to = frozenset({"seat-b"})
    piece.zone_id = PUBLIC_TABLE

    restored = from_snapshot(to_snapshot(table))
    restored_piece = restored.pieces["card-0"]

    assert restored_piece.held_by == "seat-a"
    assert restored_piece.revealed_to == frozenset({"seat-b"})
    assert restored_piece.x == 12.0
    assert restored_piece.y == 34.0


def test_round_trip_preserves_strokes() -> None:
    table = build_sample_table()
    table.strokes["stroke-1"] = Stroke(
        id="stroke-1",
        seat_id=SEAT_A,
        colour="#c81e1e",
        width=3.0,
        points=[(0.0, 0.0), (10.5, 20.25)],
        created_at=123.5,
        closed=True,
    )

    restored = from_snapshot(to_snapshot(table))

    assert restored.strokes["stroke-1"].points == [(0.0, 0.0), (10.5, 20.25)]
    assert restored.strokes["stroke-1"].closed is True


def test_applied_op_ids_round_trip() -> None:
    table = build_sample_table()
    run_op(table, SEAT_A, Grab(piece_id="card-0"))

    restored = from_snapshot(to_snapshot(table))

    assert restored.applied_op_ids == table.applied_op_ids
    assert len(restored.applied_op_ids) == 1
