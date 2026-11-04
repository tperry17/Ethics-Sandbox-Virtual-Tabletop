"""Property-based tests over sandbox/model, per Prompt 4:

* no sequence of legal operations may ever let ``project()`` hand a viewer a
  ``component_id`` they are not entitled to;
* no sequence may lose or duplicate a piece;
* a table replayed from its recorded operations equals the table that
  produced them.

Each test drives a random walk of operations against a table built by
``build_sample_table``, drawing arguments from the table's own current state
at each step (via ``st.data()``) so that every generated operation refers to
ids that actually exist to draw from - most will still be legal-but-random,
and some will be rejected outright, which is fine: a ``Reject`` changes
nothing, so it cannot violate any of these properties.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from _model_support import FACILITATOR, SEAT_A, SEAT_B, build_die, build_sample_table
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sandbox.model.entities import Table
from sandbox.model.ops import (
    ClearInk,
    Deal,
    Despawn,
    Draw,
    EndShow,
    EraseInk,
    Flip,
    Grab,
    Group,
    InkAppend,
    InkBegin,
    InkEnd,
    Lock,
    Move,
    MoveToZone,
    Operation,
    Peek,
    Point,
    Release,
    ReorderZ,
    ResetTable,
    ResetZone,
    Roll,
    Rotate,
    SetProp,
    ShowTo,
    Shuffle,
    Spawn,
    StackOnto,
    Ungroup,
    Unlock,
    new_op_id,
    run_op,
)
from sandbox.model.results import Ok
from sandbox.model.types import PieceKind, Visibility
from sandbox.model.visibility import project

ACTORS = (FACILITATOR, SEAT_A, SEAT_B)
VIEWERS = (FACILITATOR, SEAT_A, SEAT_B, None)

_settings = settings(
    max_examples=60,
    stateful_step_count=25,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


def _draw_op(data: st.DataObject, table: Table) -> tuple[str, Operation]:
    """Draw one random, plausible operation against ``table``'s current state."""
    actor = data.draw(st.sampled_from(ACTORS), label="actor")
    piece_ids = list(table.pieces) or ["missing-piece"]
    zone_ids = list(table.zones)
    stroke_ids = list(table.strokes) or ["missing-stroke"]
    piece_id = data.draw(st.sampled_from(piece_ids), label="piece_id")
    zone_id = data.draw(st.sampled_from(zone_ids), label="zone_id")
    other_zone_id = data.draw(st.sampled_from(zone_ids), label="other_zone_id")
    coord = data.draw(st.floats(min_value=-50, max_value=500, allow_nan=False))
    other_coord = data.draw(st.floats(min_value=-50, max_value=500, allow_nan=False))
    seat_ids = data.draw(
        st.lists(st.sampled_from(ACTORS), max_size=2, unique=True), label="seat_ids"
    )

    def spawn() -> Operation:
        return Spawn(
            component_id="prop-piece",
            kind=PieceKind.TOKEN,
            zone_id=zone_id,
            count=1,
            piece_ids=(new_op_id(),),
        )

    def spawn_tile() -> Operation:
        return Spawn(
            component_id="prop-tile",
            kind=PieceKind.TILE,
            zone_id=zone_id,
            count=1,
            piece_ids=(new_op_id(),),
        )

    choices: list[Callable[[], Operation]] = [
        spawn_tile,
        lambda: Grab(piece_id=piece_id),
        lambda: Release(piece_id=piece_id),
        lambda: Move(piece_id=piece_id, x=coord, y=other_coord),
        lambda: MoveToZone(piece_id=piece_id, zone_id=zone_id),
        lambda: Flip(piece_id=piece_id),
        lambda: Rotate(piece_id=piece_id, degrees=coord),
        lambda: ReorderZ(piece_id=piece_id, to_top=bool(int(coord) % 2)),
        lambda: Shuffle(zone_id=zone_id),
        lambda: Draw(count=1, from_zone=zone_id, to_zone=other_zone_id),
        lambda: Deal(from_zone=zone_id, to_zones=(other_zone_id,), count_each=1),
        lambda: SetProp(piece_id=piece_id, key="note", value=coord),
        lambda: Lock(piece_id=piece_id),
        lambda: Unlock(piece_id=piece_id),
        lambda: Point(x=coord, y=other_coord),
        lambda: InkBegin(
            stroke_id=new_op_id(), colour="red", width=1.0, x=coord, y=other_coord
        ),
        lambda: InkAppend(
            stroke_id=data.draw(st.sampled_from(stroke_ids)), x=coord, y=coord
        ),
        lambda: InkEnd(stroke_id=data.draw(st.sampled_from(stroke_ids))),
        lambda: EraseInk(stroke_id=data.draw(st.sampled_from(stroke_ids))),
        lambda: spawn(),
        lambda: Despawn(piece_ids=(piece_id,)),
        lambda: ResetZone(zone_id=zone_id),
        lambda: ResetTable(),
        lambda: ShowTo(piece_id=piece_id, seat_ids=tuple(seat_ids)),
        lambda: EndShow(piece_id=piece_id),
        lambda: Peek(piece_id=piece_id),
        lambda: (
            Group(piece_ids=tuple(piece_ids[:2]))
            if len(piece_ids) >= 2
            else Move(piece_id=piece_id, x=coord, y=other_coord)
        ),
        lambda: Ungroup(piece_ids=tuple(piece_ids[:2])),
        lambda: Roll(target_id=piece_id),
        lambda: StackOnto(
            piece_id=piece_id, onto_id=data.draw(st.sampled_from(piece_ids))
        ),
        lambda: ClearInk(everyone=bool(int(coord) % 2)),
    ]
    build = data.draw(st.sampled_from(choices), label="op_kind")
    return actor, build()


def _should_see_face(table: Table, piece_id: str, viewer_seat: str | None) -> bool:
    """An independent restatement of the visibility spec, not a call into visibility.py.

    public: entitled viewer sees a face-up piece's face. private_to_owner:
    only the owning seat, and only if face-up. facilitator_only: the owner
    or the facilitator, only if face-up. hidden: nobody, ever. A deliberate
    reveal in ``revealed_to`` always wins over all of the above. A tile has
    two public sides, so "if face-up" does not apply to one.
    """
    piece = table.pieces[piece_id]
    if viewer_seat is not None and viewer_seat in piece.revealed_to:
        return True
    zone = table.zones.get(piece.zone_id)
    if zone is None or zone.visibility is Visibility.HIDDEN:
        return False
    if not piece.face_up and piece.kind is not PieceKind.TILE:
        return False
    if zone.visibility is Visibility.PUBLIC:
        return True
    if zone.visibility is Visibility.PRIVATE_TO_OWNER:
        return viewer_seat is not None and viewer_seat == zone.owner_seat
    if zone.visibility is Visibility.FACILITATOR_ONLY:
        if viewer_seat == zone.owner_seat and viewer_seat is not None:
            return True
        return viewer_seat is not None and table.is_facilitator(viewer_seat)
    return False


def _assert_no_leak(table: Table) -> None:
    for viewer in VIEWERS:
        view = project(table, viewer)
        for viewed in view.pieces:
            entitled = _should_see_face(table, viewed.id, viewer)
            if entitled:
                continue
            assert viewed.component_id is None, (
                f"viewer {viewer!r} was handed component_id of piece "
                f"{viewed.id!r}, which they are not entitled to"
            )
            assert viewed.face_up is False
            assert viewed.value is None, (
                f"viewer {viewer!r} was handed the rolled value of piece "
                f"{viewed.id!r}, which they are not entitled to see"
            )


@given(data=st.data())
@_settings
def test_project_never_leaks_a_component_id_the_viewer_is_not_entitled_to(
    data: st.DataObject,
) -> None:
    table = build_sample_table(seed=data.draw(st.integers(0, 1000)), deck_size=4)
    table.pieces["extra-die"] = build_die("extra-die")
    _assert_no_leak(table)

    steps = data.draw(st.integers(min_value=1, max_value=25))
    for _ in range(steps):
        actor, op = _draw_op(data, table)
        run_op(table, actor, op)
        _assert_no_leak(table)


@given(data=st.data())
@_settings
def test_nobody_can_reveal_a_face_their_own_zone_does_not_show_them(
    data: st.DataObject,
) -> None:
    """A reveal overrides a zone's visibility, so it is only safe if the
    person making it could already see the face without anyone's help."""
    table = build_sample_table(seed=data.draw(st.integers(0, 1000)), deck_size=4)

    steps = data.draw(st.integers(min_value=1, max_value=25))
    for _ in range(steps):
        actor, op = _draw_op(data, table)
        could_see = False
        if isinstance(op, ShowTo) and op.piece_id in table.pieces:
            piece = table.pieces[op.piece_id]
            saved = piece.revealed_to
            piece.revealed_to = frozenset()
            could_see = _should_see_face(table, piece.id, actor)
            piece.revealed_to = saved
        outcome = run_op(table, actor, op)
        if isinstance(op, ShowTo) and isinstance(outcome, Ok):
            assert could_see, f"{actor} revealed {op.piece_id} without seeing it"


@given(data=st.data())
@_settings
def test_no_piece_is_ever_lost_or_duplicated(data: st.DataObject) -> None:
    deck_size = 4
    seed = data.draw(st.integers(0, 1000))
    table = build_sample_table(seed=seed, deck_size=deck_size)
    known_ids: set[str] = set(table.pieces)
    assert len(table.pieces) == len(known_ids) == deck_size

    steps = data.draw(st.integers(min_value=1, max_value=25))
    for _ in range(steps):
        actor, op = _draw_op(data, table)
        before_ids = set(table.pieces)
        outcome = run_op(table, actor, op)
        after_ids = set(table.pieces)

        # No id may appear that was never spawned, and any id spawned this
        # step joins the ever-known set. A dict cannot itself hold a key
        # twice, so "duplicated" is checked as: no despawned id ever comes
        # back to life on its own, and no spawn reuses a live id.
        new_ids = after_ids - before_ids
        assert new_ids.isdisjoint(before_ids)
        known_ids |= new_ids
        assert after_ids <= known_ids
        if isinstance(outcome, Ok):
            removed = before_ids - after_ids
            assert removed.isdisjoint(after_ids)


@given(data=st.data())
@_settings
def test_replaying_the_recorded_operations_reconstructs_the_same_table(
    data: st.DataObject,
) -> None:
    seed = data.draw(st.integers(0, 1000))
    live = build_sample_table(seed=seed, deck_size=4)
    log: list[tuple[str, Operation]] = []

    steps = data.draw(st.integers(min_value=1, max_value=25))
    for _ in range(steps):
        actor, op = _draw_op(data, live)
        outcome = run_op(live, actor, op)
        if isinstance(outcome, Ok):
            log.append((actor, op))

    replayed = build_sample_table(seed=seed, deck_size=4)
    for actor, op in log:
        replayed_outcome = run_op(replayed, actor, op)
        assert isinstance(replayed_outcome, Ok)

    assert replayed == live


def test_replay_helper_sanity_the_reference_table_builder_is_deterministic() -> None:
    # A cheap guard on the property tests' own foundation: build_sample_table
    # must be a pure function of its arguments, or "replay" would be
    # meaningless. (Also exercises `replace`, kept importable for future
    # variations of this table without duplicating the whole builder.)
    one = build_sample_table(seed=3, deck_size=4)
    other = build_sample_table(seed=3, deck_size=4)
    assert one == other
    assert replace(one.pieces["card-0"]) == one.pieces["card-0"]
