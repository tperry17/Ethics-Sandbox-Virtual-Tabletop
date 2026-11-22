"""Activities started inside a room: sign-up, their own zones, scoped buttons."""

from __future__ import annotations

from _games_support import hooked, pairs

from sandbox.games.engine import (
    build_activity_start,
    build_join_running,
    build_leave_running,
    build_macro,
    build_seat,
    build_table,
)
from sandbox.model import (
    EndActivity,
    JoinActivity,
    JoinRunningActivity,
    LeaveActivity,
    LeaveRunningActivity,
    MoveToZone,
    Ok,
    OpenActivity,
    Rect,
    Reject,
    SetActivityPlayers,
    Table,
    TableRng,
    TakeFacilitator,
    run_op,
)


def _room(people: int = 4) -> Table:
    """An open room: seats, and no game of its own."""
    table = Table(rng=TableRng(seed=1))
    seat_id, transaction = build_table(None, table, participant_id="p-1")
    assert isinstance(run_op(table, seat_id, transaction), Ok)
    for person in range(2, people + 1):
        seat_id, transaction = build_seat(None, table, participant_id=f"p-{person}")
        assert isinstance(run_op(table, seat_id, transaction), Ok)
    return table


def _open(table: Table, seat: str = "seat-1") -> str:
    game = pairs().definition.meta
    op = OpenActivity(
        kind=game.slug,
        title=game.title,
        min_players=game.players.min,
        max_players=game.players.max,
    )
    assert isinstance(run_op(table, seat, op), Ok)
    return next(reversed(table.activities))


def _begun(table: Table, seats: tuple[str, ...] = ("seat-1", "seat-3")) -> str:
    activity_id = _open(table, seats[0])
    for seat in seats[1:]:
        assert isinstance(run_op(table, seat, JoinActivity(activity_id)), Ok)
    built = build_activity_start(pairs(), table, seats[0], activity_id)
    assert not isinstance(built, Reject), built
    assert isinstance(run_op(table, seats[0], built), Ok)
    return activity_id


def test_the_opener_is_the_first_to_sign_up_and_the_others_may_join() -> None:
    table = _room()
    activity_id = _open(table)
    assert table.activities[activity_id].seats == ("seat-1",)
    assert isinstance(run_op(table, "seat-2", JoinActivity(activity_id)), Ok)
    assert "already" in str(run_op(table, "seat-2", JoinActivity(activity_id)))
    assert isinstance(
        run_op(table, "seat-3", JoinActivity(activity_id)), Reject
    )  # full


def test_leaving_removes_you_and_is_not_cancelling() -> None:
    table = _room()
    activity_id = _open(table)
    run_op(table, "seat-2", JoinActivity(activity_id))
    run_op(table, "seat-1", LeaveActivity(activity_id))
    assert table.activities[activity_id].seats == ("seat-2",)
    # The last one out leaves the sign-up open, for others to join.
    run_op(table, "seat-2", LeaveActivity(activity_id))
    assert table.activities[activity_id].seats == ()
    assert isinstance(run_op(table, "seat-3", JoinActivity(activity_id)), Ok)


def test_an_empty_sign_up_may_be_cancelled_by_anyone() -> None:
    table = _room()
    activity_id = _open(table)
    # While someone is signed up, only they (or the facilitator) may cancel.
    assert isinstance(run_op(table, "seat-2", EndActivity(activity_id)), Reject)
    run_op(table, "seat-1", LeaveActivity(activity_id))
    assert isinstance(run_op(table, "seat-2", EndActivity(activity_id)), Ok)
    assert not table.activities


def test_beginning_makes_zones_for_the_players_only() -> None:
    table = _room()
    activity_id = _begun(table)
    assert table.activities[activity_id].status == "running"
    zones = set(table.zones)
    assert f"{activity_id}:caught" in zones
    assert f"{activity_id}:hand-seat-1" in zones
    assert f"{activity_id}:hand-seat-3" in zones
    assert f"{activity_id}:hand-seat-2" not in zones
    assert f"{activity_id}:hand-seat-4" not in zones
    assert len(table.pieces_in_zone(f"{activity_id}:deck")) > 0


def test_an_activity_is_placed_clear_of_the_sandbox() -> None:
    table = _room()
    activity_id = _begun(table)
    own = table.zones[f"{activity_id}:caught"].geometry
    assert isinstance(own, Rect)
    others = [z.geometry for zid, z in table.zones.items() if ":" not in zid]
    assert all(own.x > g.x + g.width for g in others if isinstance(g, Rect)), (
        "an activity's zones start to the right of every sandbox zone"
    )


def test_an_activity_button_acts_only_on_its_own_zones() -> None:
    table = _room()
    activity_id = _begun(table)
    sandbox_pieces = {
        p.id: p.zone_id for p in table.pieces.values() if ":" not in p.zone_id
    }
    deal = build_macro(pairs(), table, "seat-1", "deal", activity_id)
    assert isinstance(deal, type(deal)) and not isinstance(deal, Reject), deal
    assert isinstance(run_op(table, "seat-1", deal), Ok)
    assert len(table.pieces_in_zone(f"{activity_id}:hand-seat-1")) == 3
    assert len(table.pieces_in_zone(f"{activity_id}:hand-seat-3")) == 3
    assert not table.pieces_in_zone(f"{activity_id}:hand-seat-2")
    after = {p.id: p.zone_id for p in table.pieces.values() if ":" not in p.zone_id}
    assert after == sandbox_pieces


def test_a_python_button_finds_the_activitys_zones_through_the_context() -> None:
    table = _room()
    activity_id = _begun(table)
    run_op(table, "seat-1", TakeFacilitator())  # so the test may place the cards
    for suit in ("hearts", "spades"):
        ace = next(
            p
            for p in table.pieces.values()
            if p.component_id == f"cards:ace-of-{suit}"
            and p.zone_id.startswith(f"{activity_id}:")
        )
        move = MoveToZone(piece_id=ace.id, zone_id=f"{activity_id}:hand-seat-1")
        assert isinstance(run_op(table, "seat-1", move), Ok)
    built = build_macro(pairs(), table, "seat-1", "call_pairs", activity_id)
    assert not isinstance(built, Reject), built
    assert isinstance(run_op(table, "seat-1", built), Ok)
    assert len(table.pieces_in_zone(f"{activity_id}:caught")) == 2


def test_a_facilitator_button_is_open_to_the_players_while_nobody_facilitates() -> None:
    table = _room()
    activity_id = _begun(table)
    assert not isinstance(
        build_macro(pairs(), table, "seat-3", "deal", activity_id), Reject
    )
    run_op(table, "seat-2", TakeFacilitator())
    refused = build_macro(pairs(), table, "seat-3", "deal", activity_id)
    assert isinstance(refused, Reject) and "facilitator" in refused.reason


def test_someone_outside_the_activity_cannot_press_its_buttons() -> None:
    table = _room()
    activity_id = _begun(table)
    refused = build_macro(pairs(), table, "seat-2", "deal", activity_id)
    assert isinstance(refused, Reject)


def test_two_activities_do_not_touch_each_others_zones() -> None:
    table = _room(people=4)
    first = _begun(table, ("seat-1", "seat-2"))
    second = _begun(table, ("seat-3", "seat-4"))
    assert first != second
    built = build_macro(pairs(), table, "seat-1", "deal", first)
    assert not isinstance(built, Reject)
    run_op(table, "seat-1", built)
    assert not table.pieces_in_zone(f"{second}:hand-seat-3")
    assert len(table.pieces_in_zone(f"{second}:deck")) > 0


def test_ending_takes_its_zones_and_pieces_away_and_nothing_else() -> None:
    table = _room()
    activity_id = _begun(table)
    sandbox_zones = {z for z in table.zones if ":" not in z}
    assert isinstance(run_op(table, "seat-3", EndActivity(activity_id)), Ok)
    assert not table.activities
    assert set(table.zones) == sandbox_zones
    assert not any(
        p.zone_id.startswith(f"{activity_id}:") for p in table.pieces.values()
    )
    assert isinstance(run_op(table, "seat-2", EndActivity(activity_id)), Reject)


def test_only_a_player_or_the_facilitator_may_end_it() -> None:
    table = _room()
    activity_id = _begun(table)
    assert isinstance(run_op(table, "seat-2", EndActivity(activity_id)), Reject)
    run_op(table, "seat-2", TakeFacilitator())
    assert isinstance(run_op(table, "seat-2", EndActivity(activity_id)), Ok)


def test_the_facilitator_may_choose_the_players() -> None:
    table = _room()
    activity_id = _open(table)
    chosen = SetActivityPlayers(activity_id, ("seat-2", "seat-4"))
    assert isinstance(run_op(table, "seat-3", chosen), Reject)
    run_op(table, "seat-3", TakeFacilitator())
    assert isinstance(run_op(table, "seat-3", chosen), Ok)
    assert table.activities[activity_id].seats == ("seat-2", "seat-4")
    wrong_count = SetActivityPlayers(activity_id, ("seat-2",))
    assert isinstance(run_op(table, "seat-3", wrong_count), Reject)


# -- joining an activity that has already begun -----------------------------------


def _begun_with_room(table: Table) -> str:
    """Hooked (one to three players), begun by seat-1 alone."""
    game = hooked()
    meta = game.definition.meta
    op = OpenActivity(
        kind=game.slug,
        title=meta.title,
        min_players=meta.players.min,
        max_players=meta.players.max,
    )
    assert isinstance(run_op(table, "seat-1", op), Ok)
    activity_id = next(reversed(table.activities))
    built = build_activity_start(game, table, "seat-1", activity_id)
    assert not isinstance(built, Reject), built
    assert isinstance(run_op(table, "seat-1", built), Ok)
    return activity_id


def test_someone_may_join_a_running_activity_and_gets_zones_of_their_own() -> None:
    table = _room()
    activity_id = _begun_with_room(table)
    before = set(table.activities[activity_id].zones)
    built = build_join_running(hooked(), table, "seat-2", activity_id)
    assert not isinstance(built, Reject), built
    assert isinstance(run_op(table, "seat-2", built), Ok)
    activity = table.activities[activity_id]
    assert activity.seats == ("seat-1", "seat-2")
    added = set(activity.zones) - before
    assert added, "the newcomer has no zones"
    assert {table.zones[z].owner_seat for z in added} == {"seat-2"}
    # Their tray sits beside the first player's, not on top of it.
    trays = [table.zones[z] for z in activity.zones if table.zones[z].owner_seat]
    rects = [t.geometry for t in trays if isinstance(t.geometry, Rect)]
    places = {(rect.x, rect.y) for rect in rects}
    assert len(places) == len(trays)
    # Ending it takes the newcomer's zones away with the rest.
    assert isinstance(run_op(table, "seat-1", EndActivity(activity_id)), Ok)
    assert not added & set(table.zones)


def test_joining_a_running_activity_is_refused_when_full_or_already_in_it() -> None:
    table = _room()
    activity_id = _begun_with_room(table)
    already = build_join_running(hooked(), table, "seat-1", activity_id)
    assert isinstance(already, Reject) and "already" in already.reason
    for seat in ("seat-2", "seat-3"):
        built = build_join_running(hooked(), table, seat, activity_id)
        assert not isinstance(built, Reject), built
        assert isinstance(run_op(table, seat, built), Ok)
    full = build_join_running(hooked(), table, "seat-4", activity_id)
    assert isinstance(full, Reject) and "full" in full.reason


def test_a_sign_up_is_joined_by_signing_up_not_by_joining_a_running_activity() -> None:
    table = _room()
    activity_id = _open(table)
    refused = run_op(table, "seat-2", JoinRunningActivity(activity_id, "seat-2"))
    assert "not begun" in str(refused)


def test_nobody_joins_a_running_activity_for_someone_else() -> None:
    table = _room()
    activity_id = _begun_with_room(table)
    refused = run_op(table, "seat-2", JoinRunningActivity(activity_id, "seat-3"))
    assert "yourself" in str(refused)


def test_a_player_may_leave_a_running_activity_and_the_rest_carry_on() -> None:
    table = _room()
    activity_id = _begun_with_room(table)
    joined = build_join_running(hooked(), table, "seat-2", activity_id)
    assert not isinstance(joined, Reject), joined
    assert isinstance(run_op(table, "seat-2", joined), Ok)
    theirs = {
        z
        for z in table.activities[activity_id].zones
        if table.zones[z].owner_seat == "seat-2"
    }
    assert theirs

    left = build_leave_running(hooked(), table, "seat-2", activity_id)
    assert not isinstance(left, Reject), left
    assert isinstance(run_op(table, "seat-2", left), Ok)
    activity = table.activities[activity_id]
    assert activity.status == "running"
    assert activity.seats == ("seat-1",)
    assert not theirs & set(table.zones)
    assert not theirs & set(activity.zones)

    # Nobody leaves for someone else, and the last one out leaves it ownerless:
    # then anyone may end it.
    refused = run_op(table, "seat-2", LeaveRunningActivity(activity_id, "seat-1"))
    assert "yourself" in str(refused)
    last = build_leave_running(hooked(), table, "seat-1", activity_id)
    assert not isinstance(last, Reject), last
    assert isinstance(run_op(table, "seat-1", last), Ok)
    assert isinstance(run_op(table, "seat-3", EndActivity(activity_id)), Ok)
