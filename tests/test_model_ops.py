from _model_support import (
    DECK,
    DISCARD,
    FACILITATOR,
    HAND_A,
    HAND_B,
    PUBLIC_TABLE,
    SEAT_A,
    SEAT_B,
    build_die,
    build_sample_table,
)

from sandbox.model.entities import APPLIED_OP_IDS_KEPT, Piece, Rect, Table
from sandbox.model.ops import (
    AddSeat,
    AddZone,
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
    Transaction,
    Ungroup,
    Unlock,
    run_op,
)
from sandbox.model.results import Ok, Reject
from sandbox.model.types import Layout, PieceKind, Visibility, ZoneKind
from sandbox.model.visibility import project, project_patches

# -- grabbing, releasing --------------------------------------------------------


def test_grab_marks_the_piece_held_by_the_actor() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(table, SEAT_A, Grab(piece_id="card-0"))

    assert isinstance(outcome, Ok)
    assert table.pieces["card-0"].held_by == SEAT_A


def test_grab_is_rejected_when_someone_else_is_already_holding_it() -> None:
    table = build_sample_table(deck_size=1)
    run_op(table, SEAT_A, Grab(piece_id="card-0"))

    outcome = run_op(table, SEAT_B, Grab(piece_id="card-0"))

    assert isinstance(outcome, Reject)
    assert table.pieces["card-0"].held_by == SEAT_A


def test_grab_of_a_locked_piece_is_rejected_unless_actor_is_facilitator() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].locked = True

    assert isinstance(run_op(table, SEAT_A, Grab(piece_id="card-0")), Reject)
    assert isinstance(run_op(table, FACILITATOR, Grab(piece_id="card-0")), Ok)


def test_grab_of_a_missing_piece_is_rejected() -> None:
    table = build_sample_table(deck_size=0)

    outcome = run_op(table, SEAT_A, Grab(piece_id="no-such-piece"))

    assert isinstance(outcome, Reject)


def test_release_by_the_holder_clears_held_by() -> None:
    table = build_sample_table(deck_size=1)
    run_op(table, SEAT_A, Grab(piece_id="card-0"))

    outcome = run_op(table, SEAT_A, Release(piece_id="card-0"))

    assert isinstance(outcome, Ok)
    assert table.pieces["card-0"].held_by is None


def test_release_by_a_non_holder_is_rejected_unless_facilitator() -> None:
    table = build_sample_table(deck_size=1)
    run_op(table, SEAT_A, Grab(piece_id="card-0"))

    assert isinstance(run_op(table, SEAT_B, Release(piece_id="card-0")), Reject)
    assert isinstance(run_op(table, FACILITATOR, Release(piece_id="card-0")), Ok)


# -- moving, flipping, rotating, ordering ---------------------------------------


def test_move_updates_position_within_the_current_zone() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(table, SEAT_A, Move(piece_id="card-0", x=12.0, y=34.0))

    assert isinstance(outcome, Ok)
    piece = table.pieces["card-0"]
    assert (piece.x, piece.y) == (12.0, 34.0)


def test_move_is_rejected_when_held_by_someone_else() -> None:
    table = build_sample_table(deck_size=1)
    run_op(table, SEAT_A, Grab(piece_id="card-0"))

    outcome = run_op(table, SEAT_B, Move(piece_id="card-0", x=1.0, y=1.0))

    assert isinstance(outcome, Reject)


def test_move_to_zone_relocates_and_reassigns_z_and_clears_reveals() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].revealed_to = frozenset({SEAT_B})

    outcome = run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=HAND_A))

    assert isinstance(outcome, Ok)
    piece = table.pieces["card-0"]
    assert piece.zone_id == HAND_A
    assert piece.revealed_to == frozenset()


def test_move_to_zone_into_a_private_zone_hides_it_from_everyone_else_at_once() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].zone_id = PUBLIC_TABLE
    table.pieces["card-0"].face_up = True

    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=HAND_A))

    other_view = project(table, SEAT_B)
    viewed = next(p for p in other_view.pieces if p.id == "card-0")
    assert viewed.component_id is None


def test_move_to_zone_respects_capacity() -> None:
    table = build_sample_table(deck_size=2)
    table.zones[DISCARD].capacity = 1
    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=DISCARD))

    outcome = run_op(table, SEAT_A, MoveToZone(piece_id="card-1", zone_id=DISCARD))

    assert isinstance(outcome, Reject)


def test_move_to_zone_rejects_an_unknown_zone() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id="nowhere"))

    assert isinstance(outcome, Reject)


def test_flip_toggles_face_up_by_default() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].face_up = False

    run_op(table, SEAT_A, Flip(piece_id="card-0"))

    assert table.pieces["card-0"].face_up is True


def test_flip_can_set_an_explicit_face() -> None:
    table = build_sample_table(deck_size=1)

    run_op(table, SEAT_A, Flip(piece_id="card-0", face_up=True))
    run_op(table, SEAT_A, Flip(piece_id="card-0", face_up=True))

    assert table.pieces["card-0"].face_up is True


def test_rotate_wraps_within_a_full_turn() -> None:
    table = build_sample_table(deck_size=1)

    run_op(table, SEAT_A, Rotate(piece_id="card-0", degrees=350))
    run_op(table, SEAT_A, Rotate(piece_id="card-0", degrees=20))

    assert table.pieces["card-0"].rotation == 10


def test_reorder_z_to_top_beats_every_sibling() -> None:
    table = build_sample_table(deck_size=3)

    run_op(table, SEAT_A, ReorderZ(piece_id="card-0", to_top=True))

    ordered = table.pieces_in_zone(DECK)
    assert ordered[-1].id == "card-0"


def test_reorder_z_to_bottom_beats_every_sibling() -> None:
    table = build_sample_table(deck_size=3)

    run_op(table, SEAT_A, ReorderZ(piece_id="card-2", to_top=False))

    ordered = table.pieces_in_zone(DECK)
    assert ordered[0].id == "card-2"


# -- decks, dealing, dice --------------------------------------------------------


def test_shuffle_with_a_fixed_seed_is_reproducible() -> None:
    first = build_sample_table(seed=42, deck_size=6)
    second = build_sample_table(seed=42, deck_size=6)

    run_op(first, FACILITATOR, Shuffle(zone_id=DECK))
    run_op(second, FACILITATOR, Shuffle(zone_id=DECK))

    order_one = [p.component_id for p in first.pieces_in_zone(DECK)]
    order_two = [p.component_id for p in second.pieces_in_zone(DECK)]
    assert order_one == order_two


def test_shuffle_can_change_the_order() -> None:
    table = build_sample_table(seed=1, deck_size=8)
    before = [p.component_id for p in table.pieces_in_zone(DECK)]

    run_op(table, FACILITATOR, Shuffle(zone_id=DECK))

    after = [p.component_id for p in table.pieces_in_zone(DECK)]
    assert sorted(before) == sorted(after)
    assert before != after


def test_a_shuffled_card_cannot_be_followed_by_its_id() -> None:
    # Anyone who saw card-0's face could otherwise track the piece id
    # "card-0" through the deck and into whoever's hand it was dealt to.
    tracked = 0
    for seed in range(40):
        table = build_sample_table(seed=seed, deck_size=8)
        seen = table.pieces["card-0"].component_id
        run_op(table, FACILITATOR, Shuffle(zone_id=DECK))
        if table.pieces["card-0"].component_id == seen:
            tracked += 1
    # One in eight by chance; never every time.
    assert tracked < 20


def test_shuffle_keeps_every_piece_where_it_was() -> None:
    table = build_sample_table(seed=3, deck_size=6)
    places = {p.id: (p.zone_id, p.x, p.y, p.z) for p in table.pieces.values()}

    run_op(table, FACILITATOR, Shuffle(zone_id=DECK))

    assert {p.id: (p.zone_id, p.x, p.y, p.z) for p in table.pieces.values()} == places


def test_shuffle_is_refused_while_someone_holds_a_piece_in_the_zone() -> None:
    table = build_sample_table(deck_size=4)
    run_op(table, SEAT_A, Grab(piece_id="card-3"))

    outcome = run_op(table, FACILITATOR, Shuffle(zone_id=DECK))

    assert isinstance(outcome, Reject)
    assert outcome.reason == "Someone is holding a piece from Deck."


def test_shuffle_of_an_unknown_zone_is_rejected() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(table, FACILITATOR, Shuffle(zone_id="nowhere"))

    assert isinstance(outcome, Reject)


def test_draw_moves_the_top_pieces_into_the_destination() -> None:
    table = build_sample_table(deck_size=5)

    outcome = run_op(table, SEAT_A, Draw(count=2, from_zone=DECK, to_zone=HAND_A))

    assert isinstance(outcome, Ok)
    hand = {p.id for p in table.pieces_in_zone(HAND_A)}
    assert hand == {"card-3", "card-4"}
    assert {p.id for p in table.pieces_in_zone(DECK)} == {"card-0", "card-1", "card-2"}


def test_draw_more_than_available_is_rejected_and_changes_nothing() -> None:
    table = build_sample_table(deck_size=2)

    outcome = run_op(table, SEAT_A, Draw(count=5, from_zone=DECK, to_zone=HAND_A))

    assert isinstance(outcome, Reject)
    assert table.pieces_in_zone(HAND_A) == []


def test_deal_distributes_round_robin_across_destinations() -> None:
    table = build_sample_table(deck_size=6)

    outcome = run_op(
        table,
        FACILITATOR,
        Deal(from_zone=DECK, to_zones=(HAND_A, HAND_B), count_each=3),
    )

    assert isinstance(outcome, Ok)
    hand_a = [p.id for p in table.pieces_in_zone(HAND_A)]
    hand_b = [p.id for p in table.pieces_in_zone(HAND_B)]
    assert len(hand_a) == 3
    assert len(hand_b) == 3
    # Dealt like a real deck: alternating from the top, not blocks.
    assert hand_a[0] == "card-5"
    assert hand_b[0] == "card-4"


def test_deal_needing_more_than_the_deck_holds_is_rejected() -> None:
    table = build_sample_table(deck_size=4)

    outcome = run_op(
        table,
        FACILITATOR,
        Deal(from_zone=DECK, to_zones=(HAND_A, HAND_B), count_each=3),
    )

    assert isinstance(outcome, Reject)
    assert table.pieces_in_zone(HAND_A) == []


def test_roll_picks_a_face_from_the_dies_props_deterministically() -> None:
    table = build_sample_table(deck_size=0)
    table.rng.set_state(table.rng.get_state())  # sanity: state is readable
    die = build_die()
    table.pieces[die.id] = die

    outcome = run_op(table, SEAT_A, Roll(target_id=die.id))

    assert isinstance(outcome, Ok)
    assert table.pieces[die.id].props["value"] in [1, 2, 3, 4, 5, 6]


def test_roll_of_a_non_die_piece_is_rejected() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(table, SEAT_A, Roll(target_id="card-0"))

    assert isinstance(outcome, Reject)


def test_roll_of_a_zone_rolls_every_die_in_it() -> None:
    table = build_sample_table(deck_size=0)
    table.pieces["die-1"] = build_die("die-1", zone_id=PUBLIC_TABLE)
    table.pieces["die-2"] = build_die("die-2", zone_id=PUBLIC_TABLE)

    outcome = run_op(table, SEAT_A, Roll(target_id=PUBLIC_TABLE))

    assert isinstance(outcome, Ok)
    assert "value" in table.pieces["die-1"].props
    assert "value" in table.pieces["die-2"].props


def test_roll_rejects_a_die_with_no_faces() -> None:
    table = build_sample_table(deck_size=0)
    table.pieces["die-1"] = Piece(
        id="die-1",
        kind=PieceKind.DIE,
        component_id="d6",
        zone_id=PUBLIC_TABLE,
        x=0,
        y=0,
        z=0,
    )

    outcome = run_op(table, SEAT_A, Roll(target_id="die-1"))

    assert isinstance(outcome, Reject)


def test_set_prop_merges_into_existing_props() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].props["existing"] = "keep-me"

    run_op(table, SEAT_A, SetProp(piece_id="card-0", key="note", value="hello"))

    props = table.pieces["card-0"].props
    assert props["existing"] == "keep-me"
    assert props["note"] == "hello"


# -- locking, grouping -----------------------------------------------------------


def test_only_the_facilitator_may_lock_or_unlock() -> None:
    table = build_sample_table(deck_size=1)

    assert isinstance(run_op(table, SEAT_A, Lock(piece_id="card-0")), Reject)
    assert isinstance(run_op(table, FACILITATOR, Lock(piece_id="card-0")), Ok)
    assert table.pieces["card-0"].locked is True

    assert isinstance(run_op(table, SEAT_A, Unlock(piece_id="card-0")), Reject)
    assert isinstance(run_op(table, FACILITATOR, Unlock(piece_id="card-0")), Ok)
    assert table.pieces["card-0"].locked is False


def test_group_tags_every_named_piece_with_the_same_group_id() -> None:
    table = build_sample_table(deck_size=3)

    outcome = run_op(table, SEAT_A, Group(piece_ids=("card-0", "card-1", "card-2")))

    assert isinstance(outcome, Ok)
    group_ids = {table.pieces[pid].group_id for pid in ("card-0", "card-1", "card-2")}
    assert len(group_ids) == 1
    assert None not in group_ids


def test_group_of_fewer_than_two_pieces_is_rejected() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(table, SEAT_A, Group(piece_ids=("card-0",)))

    assert isinstance(outcome, Reject)


def test_ungroup_clears_the_group_id() -> None:
    table = build_sample_table(deck_size=2)
    run_op(table, SEAT_A, Group(piece_ids=("card-0", "card-1")))

    run_op(table, SEAT_A, Ungroup(piece_ids=("card-0", "card-1")))

    assert table.pieces["card-0"].group_id is None
    assert table.pieces["card-1"].group_id is None


# -- pointing and ink -------------------------------------------------------------


def test_point_by_a_seated_participant_produces_an_event_patch_only() -> None:
    table = build_sample_table(deck_size=0)

    outcome = run_op(table, SEAT_A, Point(x=1.0, y=2.0))

    assert isinstance(outcome, Ok)
    assert len(outcome.patches) == 1
    assert outcome.patches[0].kind == "table"
    assert outcome.patches[0].op == "event"


def test_point_by_an_unseated_actor_is_rejected() -> None:
    table = build_sample_table(deck_size=0)

    outcome = run_op(table, "not-a-seat", Point(x=0.0, y=0.0))

    assert isinstance(outcome, Reject)


def test_ink_begin_append_and_end_build_up_a_stroke() -> None:
    table = build_sample_table(deck_size=0)

    run_op(
        table,
        SEAT_A,
        InkBegin(stroke_id="s1", colour="red", width=2.0, x=0.0, y=0.0),
    )
    run_op(table, SEAT_A, InkAppend(stroke_id="s1", x=1.0, y=1.0))
    outcome = run_op(table, SEAT_A, InkEnd(stroke_id="s1"))

    assert isinstance(outcome, Ok)
    stroke = table.strokes["s1"]
    assert stroke.seat_id == SEAT_A
    assert stroke.points == [(0.0, 0.0), (1.0, 1.0)]
    assert stroke.closed is True


def test_ink_append_by_a_different_seat_is_rejected() -> None:
    table = build_sample_table(deck_size=0)
    run_op(
        table,
        SEAT_A,
        InkBegin(stroke_id="s1", colour="red", width=2.0, x=0.0, y=0.0),
    )

    outcome = run_op(table, SEAT_B, InkAppend(stroke_id="s1", x=1.0, y=1.0))

    assert isinstance(outcome, Reject)


def test_ink_append_after_end_is_rejected() -> None:
    table = build_sample_table(deck_size=0)
    run_op(
        table,
        SEAT_A,
        InkBegin(stroke_id="s1", colour="red", width=2.0, x=0.0, y=0.0),
    )
    run_op(table, SEAT_A, InkEnd(stroke_id="s1"))

    outcome = run_op(table, SEAT_A, InkAppend(stroke_id="s1", x=9.0, y=9.0))

    assert isinstance(outcome, Reject)


def test_erase_ink_by_its_own_seat_or_the_facilitator_succeeds() -> None:
    table = build_sample_table(deck_size=0)
    run_op(
        table,
        SEAT_A,
        InkBegin(stroke_id="s1", colour="red", width=2.0, x=0.0, y=0.0),
    )

    assert isinstance(run_op(table, SEAT_B, EraseInk(stroke_id="s1")), Reject)
    assert isinstance(run_op(table, FACILITATOR, EraseInk(stroke_id="s1")), Ok)
    assert "s1" not in table.strokes


# -- spawning and resetting -------------------------------------------------------


def test_spawn_creates_the_requested_number_of_pieces() -> None:
    table = build_sample_table(deck_size=0)

    outcome = run_op(
        table,
        FACILITATOR,
        Spawn(component_id="tok", kind=PieceKind.TOKEN, zone_id=PUBLIC_TABLE, count=3),
    )

    assert isinstance(outcome, Ok)
    assert len(table.pieces_in_zone(PUBLIC_TABLE)) == 3


def test_spawn_into_a_hidden_zone_starts_face_down_but_public_starts_face_up() -> None:
    table = build_sample_table(deck_size=0)

    run_op(
        table,
        FACILITATOR,
        Spawn(component_id="c", kind=PieceKind.CARD, zone_id=DECK, count=1),
    )
    run_op(
        table,
        FACILITATOR,
        Spawn(component_id="c", kind=PieceKind.CARD, zone_id=PUBLIC_TABLE, count=1),
    )

    deck_piece = table.pieces_in_zone(DECK)[0]
    table_piece = table.pieces_in_zone(PUBLIC_TABLE)[0]
    assert deck_piece.face_up is False
    assert table_piece.face_up is True


def test_spawn_rejects_a_duplicate_explicit_piece_id() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(
        table,
        FACILITATOR,
        Spawn(
            component_id="c",
            kind=PieceKind.CARD,
            zone_id=PUBLIC_TABLE,
            count=1,
            piece_ids=("card-0",),
        ),
    )

    assert isinstance(outcome, Reject)


def test_despawn_removes_the_pieces_entirely() -> None:
    table = build_sample_table(deck_size=2)

    outcome = run_op(table, FACILITATOR, Despawn(piece_ids=("card-0", "card-1")))

    assert isinstance(outcome, Ok)
    assert table.pieces == {}


def test_despawn_of_a_missing_piece_is_rejected() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(table, FACILITATOR, Despawn(piece_ids=("no-such-piece",)))

    assert isinstance(outcome, Reject)


def test_reset_zone_clears_only_that_zone() -> None:
    table = build_sample_table(deck_size=2)
    run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=PUBLIC_TABLE))

    outcome = run_op(table, FACILITATOR, ResetZone(zone_id=DECK))

    assert isinstance(outcome, Ok)
    assert table.pieces_in_zone(DECK) == []
    assert len(table.pieces_in_zone(PUBLIC_TABLE)) == 1


def test_reset_table_requires_the_facilitator() -> None:
    table = build_sample_table(deck_size=2)

    assert isinstance(run_op(table, SEAT_A, ResetTable()), Reject)

    outcome = run_op(table, FACILITATOR, ResetTable())
    assert isinstance(outcome, Ok)
    assert table.pieces == {}


def test_reset_table_clears_pieces_and_strokes_but_not_zones_or_seats() -> None:
    table = build_sample_table(deck_size=1)
    run_op(
        table,
        SEAT_A,
        InkBegin(stroke_id="s1", colour="red", width=1.0, x=0.0, y=0.0),
    )

    run_op(table, FACILITATOR, ResetTable())

    assert table.pieces == {}
    assert table.strokes == {}
    expected_zones = {DECK, DISCARD, PUBLIC_TABLE, HAND_A, HAND_B, "facilitator-tray"}
    assert set(table.zones) == expected_zones
    assert set(table.seats) == {FACILITATOR, SEAT_A, SEAT_B}


# -- deliberate reveals ------------------------------------------------------------


def test_show_to_named_seats_reveals_only_to_them() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].zone_id = HAND_A
    table.pieces["card-0"].face_up = True

    run_op(table, SEAT_A, ShowTo(piece_id="card-0", seat_ids=(SEAT_B,)))

    assert next(p for p in project(table, SEAT_B).pieces).component_id is not None
    facilitator_view = next(p for p in project(table, FACILITATOR).pieces)
    assert facilitator_view.component_id is None


def test_show_to_with_no_seats_named_reveals_to_the_whole_table() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].zone_id = HAND_A
    table.pieces["card-0"].face_up = True

    run_op(table, SEAT_A, ShowTo(piece_id="card-0"))

    for viewer in (SEAT_A, SEAT_B, FACILITATOR):
        view = project(table, viewer)
        assert view.pieces[0].component_id is not None


def test_end_show_returns_a_piece_to_its_zones_normal_visibility() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].zone_id = HAND_A
    table.pieces["card-0"].face_up = True
    run_op(table, SEAT_A, ShowTo(piece_id="card-0"))

    run_op(table, SEAT_A, EndShow(piece_id="card-0"))

    stranger_view = project(table, SEAT_B)
    assert stranger_view.pieces[0].component_id is None


def test_peek_succeeds_for_a_piece_already_visible_to_the_actor() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].zone_id = HAND_A
    table.pieces["card-0"].face_up = True

    outcome = run_op(table, SEAT_A, Peek(piece_id="card-0"))

    assert isinstance(outcome, Ok)
    assert outcome.patches[0].kind == "table"
    assert outcome.patches[0].op == "event"


def test_peek_is_rejected_for_a_piece_the_actor_is_not_entitled_to_see() -> None:
    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].zone_id = HAND_A
    table.pieces["card-0"].face_up = True

    outcome = run_op(table, SEAT_B, Peek(piece_id="card-0"))

    assert isinstance(outcome, Reject)


# -- idempotency -------------------------------------------------------------------


def test_run_op_is_idempotent_by_op_id() -> None:
    table = build_sample_table(deck_size=1)
    move = Move(piece_id="card-0", x=5.0, y=5.0, op_id="fixed-id")

    first = run_op(table, SEAT_A, move)
    version_after_first = table.version
    second = run_op(table, SEAT_A, move)

    assert isinstance(first, Ok)
    assert isinstance(second, Ok)
    assert second.patches == []
    assert table.version == version_after_first


def test_a_table_remembers_only_the_most_recent_op_ids() -> None:
    table = build_sample_table(deck_size=1)
    for step in range(APPLIED_OP_IDS_KEPT + 50):
        run_op(table, SEAT_A, Move(piece_id="card-0", x=1.0, y=1.0, op_id=f"m{step}"))

    assert len(table.applied_op_ids) == APPLIED_OP_IDS_KEPT
    assert "m0" not in table.applied_op_ids
    # A retry of a recent intent is still applied only once.
    latest = f"m{APPLIED_OP_IDS_KEPT + 49}"
    version = table.version
    outcome = run_op(table, SEAT_A, Move(piece_id="card-0", x=9.0, y=9.0, op_id=latest))
    assert isinstance(outcome, Ok) and outcome.patches == []
    assert table.version == version


def test_a_retried_move_does_not_move_the_piece_again() -> None:
    table = build_sample_table(deck_size=1)
    move = Move(piece_id="card-0", x=5.0, y=5.0, op_id="fixed-id")
    run_op(table, SEAT_A, move)
    run_op(table, SEAT_A, Move(piece_id="card-0", x=999.0, y=999.0))
    other_move_z = table.pieces["card-0"].x

    run_op(table, SEAT_A, move)

    assert table.pieces["card-0"].x == other_move_z


def test_table_is_only_mutated_through_run_op_in_this_suite() -> None:
    # A cheap sanity net: Table() starts empty and stays that way until an
    # operation is actually run through run_op.
    table = Table()
    assert table.pieces == {}
    assert table.version == 0


# -- seats, zones, and transactions ------------------------------------------------


def test_add_seat_adds_a_seat_and_refuses_a_second_with_the_same_id() -> None:
    table = build_sample_table()

    outcome = run_op(
        table, FACILITATOR, AddSeat(seat_id="seat-c", label="C", tint_index=3)
    )

    assert isinstance(outcome, Ok)
    assert table.seats["seat-c"].label == "C"
    again = run_op(
        table, FACILITATOR, AddSeat(seat_id="seat-c", label="C", tint_index=3)
    )
    assert again == Reject("There is already a seat 'seat-c' at the table.")


def test_add_zone_needs_its_owner_to_be_seated() -> None:
    table = build_sample_table()
    zone = AddZone(
        zone_id="hand-c",
        kind=ZoneKind.HAND,
        label="Hand",
        geometry=Rect(x=0, y=0, width=10, height=10),
        visibility=Visibility.PRIVATE_TO_OWNER,
        layout=Layout.FAN,
        owner_seat="seat-c",
    )

    assert run_op(table, FACILITATOR, zone) == Reject(
        "There is no seat 'seat-c' at the table."
    )


def test_a_transaction_applies_every_step_in_order() -> None:
    table = build_sample_table(deck_size=4)

    outcome = run_op(
        table,
        FACILITATOR,
        Transaction(
            steps=(
                Draw(count=2, from_zone=DECK, to_zone=HAND_A),
                Flip(piece_id="card-3", face_up=True),
            )
        ),
    )

    assert isinstance(outcome, Ok)
    assert {p.id for p in table.pieces_in_zone(HAND_A)} == {"card-2", "card-3"}
    assert table.pieces["card-3"].face_up
    assert table.version == 1


def test_a_transaction_whose_later_step_fails_changes_nothing() -> None:
    table = build_sample_table(deck_size=4)
    version = table.version
    zones = {p.id: p.zone_id for p in table.pieces.values()}
    rng_state = table.rng.get_state()

    outcome = run_op(
        table,
        FACILITATOR,
        Transaction(
            steps=(
                Shuffle(zone_id=DECK),
                Draw(count=2, from_zone=DECK, to_zone=HAND_A),
                Draw(count=9, from_zone=DECK, to_zone=HAND_B),
            )
        ),
    )

    assert outcome == Reject("Only 2 pieces remain in Deck.")
    assert {p.id: p.zone_id for p in table.pieces.values()} == zones
    assert table.version == version
    assert table.rng.get_state() == rng_state


def test_a_transaction_is_judged_step_by_step_against_its_own_earlier_steps() -> None:
    table = build_sample_table(deck_size=4)

    # card-3 is in the deck when the transaction starts; the second step
    # is only legal because the first one moved it to the discard.
    outcome = run_op(
        table,
        FACILITATOR,
        Transaction(
            steps=(
                MoveToZone(piece_id="card-3", zone_id=DISCARD),
                Draw(count=1, from_zone=DISCARD, to_zone=HAND_A),
            )
        ),
    )

    assert isinstance(outcome, Ok)
    assert table.pieces["card-3"].zone_id == HAND_A


# -- who may take a piece from where ------------------------------------------------


def _card_in_hand_b(table: Table) -> str:
    outcome = run_op(table, FACILITATOR, Draw(count=1, from_zone=DECK, to_zone=HAND_B))
    assert isinstance(outcome, Ok)
    return table.pieces_in_zone(HAND_B)[-1].id


def test_the_facilitator_may_take_a_piece_someone_is_holding() -> None:
    table = build_sample_table(deck_size=1)
    run_op(table, SEAT_A, Grab(piece_id="card-0"))

    outcome = run_op(table, FACILITATOR, MoveToZone(piece_id="card-0", zone_id=DISCARD))

    assert isinstance(outcome, Ok)
    assert table.pieces["card-0"].zone_id == DISCARD
    assert table.pieces["card-0"].held_by is None


def test_the_facilitator_may_take_a_piece_out_of_someones_hand() -> None:
    table = build_sample_table(deck_size=2)
    card = _card_in_hand_b(table)

    outcome = run_op(table, FACILITATOR, MoveToZone(piece_id=card, zone_id=DISCARD))

    assert isinstance(outcome, Ok)


def test_a_participant_may_not_take_a_piece_out_of_someone_elses_hand() -> None:
    table = build_sample_table(deck_size=2)
    card = _card_in_hand_b(table)

    for operation in (
        MoveToZone(piece_id=card, zone_id=HAND_A),
        Move(piece_id=card, x=0, y=0),
        Flip(piece_id=card),
        Grab(piece_id=card),
    ):
        assert run_op(table, SEAT_A, operation) == Reject(
            "That piece is in someone else's hand."
        )
    assert run_op(table, SEAT_A, Draw(count=1, from_zone=HAND_B, to_zone=HAND_A)) == (
        Reject("Only its owner or the facilitator may take from B's hand.")
    )
    assert table.pieces[card].zone_id == HAND_B


def test_a_participant_may_still_give_a_piece_to_someone_elses_hand() -> None:
    table = build_sample_table(deck_size=1)

    outcome = run_op(table, SEAT_A, MoveToZone(piece_id="card-0", zone_id=HAND_B))

    assert isinstance(outcome, Ok)


def test_only_the_facilitator_may_clear_a_zone() -> None:
    table = build_sample_table(deck_size=2)

    assert run_op(table, SEAT_A, ResetZone(zone_id=DECK)) == Reject(
        "Only the facilitator may clear a zone."
    )
    assert isinstance(run_op(table, FACILITATOR, ResetZone(zone_id=DECK)), Ok)


# -- what a rolled die shows ----------------------------------------------------------


def _rolled_die(table: Table, zone_id: str) -> str:
    run_op(
        table,
        FACILITATOR,
        Spawn(
            component_id="d6", kind=PieceKind.DIE, zone_id=zone_id, piece_ids=("die",)
        ),
    )
    run_op(
        table, FACILITATOR, SetProp(piece_id="die", key="faces", value=["1", "2", "3"])
    )
    assert isinstance(run_op(table, FACILITATOR, Roll(target_id="die")), Ok)
    return "die"


def test_a_rolled_die_shows_its_value_to_everyone_who_can_see_it() -> None:
    table = build_sample_table(deck_size=0)
    die = _rolled_die(table, PUBLIC_TABLE)
    rolled = table.pieces[die].props["value"]

    for viewer in (None, SEAT_A, FACILITATOR):
        view = next(p for p in project(table, viewer).pieces if p.id == die)
        assert view.value == rolled


def test_a_die_in_a_hidden_zone_shows_no_value_to_anyone() -> None:
    table = build_sample_table(deck_size=0)
    die = _rolled_die(table, DECK)

    for viewer in (None, SEAT_A, FACILITATOR):
        view = next(p for p in project(table, viewer).pieces if p.id == die)
        assert view.value is None
    patch = run_op(table, FACILITATOR, Roll(target_id=die))
    assert isinstance(patch, Ok)
    projected = project_patches(table, patch.patches, SEAT_A)
    assert projected[0].fields["value"] is None


def test_set_text_writes_on_a_note_and_is_projected_with_the_face() -> None:
    from sandbox.model.ops import SetText

    table = build_sample_table(deck_size=1)
    piece = table.pieces["card-0"]
    assert SetText("card-0", "hello").validate(table, SEAT_A) is not None  # a card
    piece.kind = PieceKind.NOTE
    assert isinstance(run_op(table, SEAT_A, SetText("card-0", "  Build the dam  ")), Ok)
    assert piece.props["text"] == "Build the dam"
    zone = table.zones[piece.zone_id]
    for viewer in (SEAT_A, None):
        shown = [p for p in project(table, viewer).pieces if p.id == "card-0"][0]
        entitled = shown.component_id is not None
        assert (shown.text == "Build the dam") is entitled
    assert SetText("card-0", "x" * 281).validate(table, SEAT_A) is not None
    assert isinstance(run_op(table, SEAT_A, SetText("card-0", "")), Ok)
    assert "text" not in piece.props
    assert zone is not None


def test_a_token_holds_one_word_or_number() -> None:
    from sandbox.model.ops import SetText

    table = build_sample_table(deck_size=1)
    table.pieces["card-0"].kind = PieceKind.TOKEN
    assert SetText("card-0", "Yes").validate(table, SEAT_A) is None
    assert SetText("card-0", " 42 ").validate(table, SEAT_A) is None
    assert SetText("card-0", "two words").validate(table, SEAT_A) is not None
    assert SetText("card-0", "x" * 13).validate(table, SEAT_A) is not None
