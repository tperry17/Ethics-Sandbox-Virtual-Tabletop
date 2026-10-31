"""Activities started inside a room: sign-up, their own zones, scoped buttons."""

from __future__ import annotations

from _games_support import two_doors

from sandbox.games.engine import (
    build_activity_start,
    build_macro,
    build_seat,
    build_table,
)
from sandbox.model import (
    EndActivity,
    JoinActivity,
    LeaveActivity,
    Ok,
    OpenActivity,
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
    game = two_doors().definition.meta
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
    built = build_activity_start(two_doors(), table, seats[0], activity_id)
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


def test_leaving_removes_you_and_the_last_one_out_closes_it() -> None:
    table = _room()
    activity_id = _open(table)
    run_op(table, "seat-2", JoinActivity(activity_id))
    run_op(table, "seat-1", LeaveActivity(activity_id))
    assert table.activities[activity_id].seats == ("seat-2",)
    run_op(table, "seat-2", LeaveActivity(activity_id))
    assert not table.activities


def test_beginning_makes_zones_for_the_players_only() -> None:
    table = _room()
    activity_id = _begun(table)
    assert table.activities[activity_id].status == "running"
    zones = set(table.zones)
    assert f"{activity_id}:doors" in zones
    assert f"{activity_id}:hand-seat-1" in zones
    assert f"{activity_id}:hand-seat-3" in zones
    assert f"{activity_id}:hand-seat-2" not in zones
    assert f"{activity_id}:hand-seat-4" not in zones
    assert len(table.pieces_in_zone(f"{activity_id}:deck")) > 0


def test_an_activity_is_placed_clear_of_the_sandbox() -> None:
    table = _room()
    activity_id = _begun(table)
    own = table.zones[f"{activity_id}:doors"].geometry
    others = [z.geometry for zid, z in table.zones.items() if ":" not in zid]
    assert all(own.y > g.y + g.height for g in others if hasattr(g, "height"))  # type: ignore[union-attr]


def test_an_activity_button_acts_only_on_its_own_zones() -> None:
    table = _room()
    activity_id = _begun(table)
    sandbox_pieces = {
        p.id: p.zone_id for p in table.pieces.values() if ":" not in p.zone_id
    }
    deal = build_macro(two_doors(), table, "seat-1", "deal", activity_id)
    assert isinstance(deal, type(deal)) and not isinstance(deal, Reject), deal
    assert isinstance(run_op(table, "seat-1", deal), Ok)
    assert len(table.pieces_in_zone(f"{activity_id}:hand-seat-1")) == 1
    assert len(table.pieces_in_zone(f"{activity_id}:hand-seat-3")) == 1
    assert not table.pieces_in_zone(f"{activity_id}:hand-seat-2")
    after = {p.id: p.zone_id for p in table.pieces.values() if ":" not in p.zone_id}
    assert after == sandbox_pieces


def test_a_python_button_finds_the_activitys_zones_through_the_context() -> None:
    table = _room()
    activity_id = _begun(table)
    for macro in ("deal", "reveal"):
        built = build_macro(two_doors(), table, "seat-1", macro, activity_id)
        assert not isinstance(built, Reject), built
        assert isinstance(run_op(table, "seat-1", built), Ok)
    assert len(table.pieces_in_zone(f"{activity_id}:doors")) == 2


def test_a_facilitator_button_is_open_to_the_players_while_nobody_facilitates() -> None:
    table = _room()
    activity_id = _begun(table)
    assert not isinstance(
        build_macro(two_doors(), table, "seat-3", "deal", activity_id), Reject
    )
    run_op(table, "seat-2", TakeFacilitator())
    refused = build_macro(two_doors(), table, "seat-3", "deal", activity_id)
    assert isinstance(refused, Reject) and "facilitator" in refused.reason


def test_someone_outside_the_activity_cannot_press_its_buttons() -> None:
    table = _room()
    activity_id = _begun(table)
    refused = build_macro(two_doors(), table, "seat-2", "deal", activity_id)
    assert isinstance(refused, Reject)


def test_two_activities_do_not_touch_each_others_zones() -> None:
    table = _room(people=4)
    first = _begun(table, ("seat-1", "seat-2"))
    second = _begun(table, ("seat-3", "seat-4"))
    assert first != second
    built = build_macro(two_doors(), table, "seat-1", "deal", first)
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
