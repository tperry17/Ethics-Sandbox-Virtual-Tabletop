"""Classes: one activity at several tables, run by the facilitator."""

from __future__ import annotations

from _games_support import pairs

from sandbox.games.engine import build_activity_start, build_seat, build_table
from sandbox.model import (
    AssignClassTables,
    ChangeActivitySeats,
    ClearClassTimer,
    EndClass,
    JoinActivity,
    LeaveActivity,
    Ok,
    PairTables,
    PushClassPrompt,
    Reject,
    SetClassDecision,
    StartClass,
    StartClassTimer,
    Table,
    TableRng,
    TakeFacilitator,
    UnpairTables,
    run_op,
    sort_into_tables,
)


def _room(people: int = 7) -> Table:
    table = Table(rng=TableRng(seed=1))
    seat_id, transaction = build_table(None, table, participant_id="p-1")
    assert isinstance(run_op(table, seat_id, transaction), Ok)
    for person in range(2, people + 1):
        seat_id, transaction = build_seat(None, table, participant_id=f"p-{person}")
        assert isinstance(run_op(table, seat_id, transaction), Ok)
    assert isinstance(run_op(table, "seat-1", TakeFacilitator()), Ok)
    return table


def _class(table: Table, tables: int = 3) -> str:
    meta = pairs().definition.meta
    op = StartClass(
        kind=meta.slug,
        title=meta.title,
        min_players=meta.players.min,
        max_players=meta.players.max,
        tables=tables,
    )
    assert isinstance(run_op(table, "seat-1", op), Ok)
    return next(reversed(table.classes))


def test_a_class_makes_every_table_or_none() -> None:
    table = _room()
    class_id = _class(table, 3)
    group = table.classes[class_id]
    assert len(group.tables) == 3
    assert all(table.activities[t].class_id == class_id for t in group.tables)
    assert all(table.activities[t].seats == () for t in group.tables)
    refused = StartClass("pairs", "Pairs", 2, 4, tables=0)
    before = len(table.activities)
    assert isinstance(run_op(table, "seat-1", refused), Reject)
    assert len(table.activities) == before


def test_only_the_facilitator_runs_a_class() -> None:
    table = _room()
    class_id = _class(table)
    tid = table.classes[class_id].tables[0]
    start = StartClass("pairs", "Pairs", 2, 4, tables=2)
    for op in (
        start,
        StartClassTimer(class_id, 60, now=0.0),
        ClearClassTimer(class_id),
        PushClassPrompt(class_id, "Why?"),
        PairTables(class_id, tid, table.classes[class_id].tables[1]),
        SetClassDecision(class_id, tid, "x"),
        AssignClassTables(class_id, ((), (), ())),
        EndClass(class_id),
    ):
        assert isinstance(run_op(table, "seat-2", op), Reject), op


def test_the_facilitator_does_not_sit_at_a_table() -> None:
    table = _room()
    class_id = _class(table)
    tid = table.classes[class_id].tables[0]
    assert isinstance(run_op(table, "seat-1", JoinActivity(tid)), Reject)
    assigned = AssignClassTables(class_id, (("seat-1", "seat-2"), (), ()))
    assert isinstance(run_op(table, "seat-1", assigned), Reject)


def test_a_person_has_one_table_and_an_empty_table_stays() -> None:
    table = _room()
    class_id = _class(table)
    first, second, _ = table.classes[class_id].tables
    assert isinstance(run_op(table, "seat-2", JoinActivity(first)), Ok)
    assert isinstance(run_op(table, "seat-2", JoinActivity(second)), Reject)
    assert isinstance(run_op(table, "seat-2", LeaveActivity(first)), Ok)
    assert first in table.activities


def test_assigning_seats_people_and_refuses_duplicates() -> None:
    table = _room()
    class_id = _class(table)
    ok = AssignClassTables(class_id, (("seat-2", "seat-3"), ("seat-4",), ()))
    assert isinstance(run_op(table, "seat-1", ok), Ok)
    twice = AssignClassTables(class_id, (("seat-2",), ("seat-2",), ()))
    assert isinstance(run_op(table, "seat-1", twice), Reject)
    wrong_count = AssignClassTables(class_id, (("seat-2",),))
    assert isinstance(run_op(table, "seat-1", wrong_count), Reject)


def test_no_one_is_moved_after_a_table_begins() -> None:
    table = _room()
    class_id = _class(table)
    first = table.classes[class_id].tables[0]
    seated = AssignClassTables(class_id, (("seat-2", "seat-3"), (), ()))
    assert isinstance(run_op(table, "seat-1", seated), Ok)
    built = build_activity_start(pairs(), table, "seat-1", first)
    assert not isinstance(built, Reject), built
    assert isinstance(run_op(table, "seat-1", built), Ok)
    again = AssignClassTables(class_id, (("seat-4", "seat-5"), (), ()))
    assert isinstance(run_op(table, "seat-1", again), Reject)


def test_sort_is_even_within_ranges_and_reproducible() -> None:
    people = [f"seat-{n}" for n in range(1, 25)]
    tables = sort_into_tables(people, [(3, 3)] * 8, TableRng(seed=5))
    assert not isinstance(tables, str)
    assert [len(t) for t in tables] == [3] * 8
    assert sorted(p for t in tables for p in t) == sorted(people)
    again = sort_into_tables(people, [(3, 3)] * 8, TableRng(seed=5))
    assert again == tables
    uneven = sort_into_tables(people[:23], [(9, 20), (9, 20)], TableRng(seed=1))
    assert not isinstance(uneven, str)
    assert sorted(len(t) for t in uneven) == [11, 12]


def test_sort_says_why_it_cannot() -> None:
    people = [f"seat-{n}" for n in range(1, 10)]
    assert isinstance(sort_into_tables(people, [(3, 3)] * 2, TableRng(seed=1)), str)
    assert isinstance(sort_into_tables(people[:4], [(3, 3)] * 2, TableRng(seed=1)), str)


def test_timer_and_prompt_change_nothing_on_the_table() -> None:
    table = _room()
    class_id = _class(table)
    pieces, zones = dict(table.pieces), dict(table.zones)
    assert isinstance(run_op(table, "seat-1", StartClassTimer(class_id, 30, 100.0)), Ok)
    group = table.classes[class_id]
    assert group.timer_ends_at == 130.0
    assert isinstance(run_op(table, "seat-1", PushClassPrompt(class_id, "Why?")), Ok)
    assert group.prompt == "Why?"
    assert isinstance(run_op(table, "seat-1", ClearClassTimer(class_id)), Ok)
    assert group.timer_ends_at is None
    assert table.pieces == pieces and table.zones == zones
    assert isinstance(
        run_op(table, "seat-1", StartClassTimer(class_id, 0, 1.0)), Reject
    )


def test_pairing_and_decisions() -> None:
    table = _room()
    class_id = _class(table)
    a, b, c = table.classes[class_id].tables
    assert isinstance(run_op(table, "seat-1", PairTables(class_id, a, a)), Reject)
    assert isinstance(run_op(table, "seat-1", PairTables(class_id, a, b)), Ok)
    assert isinstance(run_op(table, "seat-1", PairTables(class_id, a, c)), Reject)
    assert isinstance(
        run_op(table, "seat-1", SetClassDecision(class_id, a, "Attack")), Ok
    )
    assert table.classes[class_id].decisions == {a: "Attack"}
    assert isinstance(run_op(table, "seat-1", UnpairTables(class_id, b)), Ok)
    assert table.classes[class_id].pairs == ()
    assert table.classes[class_id].decisions == {}


def test_ending_a_class_takes_its_tables_away() -> None:
    table = _room()
    class_id = _class(table)
    assert isinstance(run_op(table, "seat-1", EndClass(class_id)), Ok)
    assert not table.classes and not table.activities


def test_the_democracy_simulation_pairs_only_scenario_two() -> None:
    from sandbox.games import GAMES
    from sandbox.games.pairing import may_pair, pair_outcome, pairing_choices

    game = GAMES["democracy-simulation"]
    assert may_pair(game, {"city": "potamosia", "phase": "2"})
    assert not may_pair(game, {"city": "potamosia", "phase": "1"})
    assert pairing_choices(game, {"phase": "2"}) == ("Attack", "Defenses", "Diplomacy")
    text = pair_outcome(game, "Attack", "Diplomacy")
    assert text is not None and "Catastrophic for the defender" in text
    assert pair_outcome(game, "Attack", "Nothing") is None
    assert not may_pair(GAMES["value-cards-trading"], {})


def test_a_class_survives_a_snapshot() -> None:
    from sandbox.db.snapshot import from_snapshot, to_snapshot

    table = _room()
    class_id = _class(table)
    a, b, _ = table.classes[class_id].tables
    for op in (
        PairTables(class_id, a, b),
        SetClassDecision(class_id, a, "Attack"),
        StartClassTimer(class_id, 90, 10.0),
        PushClassPrompt(class_id, "Why?"),
    ):
        assert isinstance(run_op(table, "seat-1", op), Ok)
    again = from_snapshot(to_snapshot(table))
    assert again.classes == table.classes
    assert again.activities == table.activities


def _begun_class(table: Table) -> tuple[str, str, str]:
    """A class of two Pairs tables with seat-2/3 and seat-4/5, both begun."""
    class_id = _class(table, 2)
    first, second = table.classes[class_id].tables
    seated = AssignClassTables(class_id, (("seat-2", "seat-3"), ("seat-4", "seat-5")))
    assert isinstance(run_op(table, "seat-1", seated), Ok)
    for activity_id in (first, second):
        built = build_activity_start(pairs(), table, "seat-1", activity_id)
        assert not isinstance(built, Reject), built
        assert isinstance(run_op(table, "seat-1", built), Ok)
    return class_id, first, second


def test_the_facilitator_moves_a_person_between_begun_tables() -> None:
    from sandbox.games.engine import build_seat_move

    table = _room()
    class_id, first, second = _begun_class(table)
    # Make room at the second table, then bring seat-2 over.
    out = build_seat_move(pairs(), table, "seat-1", "seat-5", None)
    assert not isinstance(out, Reject), out
    assert isinstance(run_op(table, "seat-1", out), Ok)
    assert table.activities[second].seats == ("seat-4",)
    assert not any(z.endswith("-seat-5") for z in table.activities[second].zones)
    assert f"{second}:hand-seat-5" not in table.zones

    moved = build_seat_move(pairs(), table, "seat-1", "seat-2", second)
    assert not isinstance(moved, Reject), moved
    assert isinstance(run_op(table, "seat-1", moved), Ok)
    assert table.activities[first].seats == ("seat-3",)
    assert table.activities[second].seats == ("seat-4", "seat-2")
    assert f"{second}:hand-seat-2" in table.zones
    assert f"{first}:hand-seat-2" not in table.zones
    assert f"{second}:hand-seat-2" in table.activities[second].zones
    # The new hand does not sit on top of seat-4's.
    here = table.zones[f"{second}:hand-seat-2"].geometry
    there = table.zones[f"{second}:hand-seat-4"].geometry
    assert here != there


def test_a_person_cannot_be_at_two_tables_and_only_the_facilitator_moves() -> None:
    from sandbox.games.engine import build_seat_move

    table = _room()
    class_id, first, second = _begun_class(table)
    full = build_seat_move(pairs(), table, "seat-1", "seat-2", second)
    assert isinstance(full, Reject)  # the second table is full
    direct = ChangeActivitySeats(second, ("seat-4", "seat-5", "seat-2"))
    assert isinstance(run_op(table, "seat-1", direct), Reject)
    sneaky = ChangeActivitySeats(first, ("seat-2",))
    assert isinstance(run_op(table, "seat-2", sneaky), Reject)


def test_people_at_a_paired_table_record_its_decision() -> None:
    table = _room()
    class_id, first, second = _begun_class(table)
    decide = SetClassDecision(class_id, first, "Attack")
    assert isinstance(run_op(table, "seat-2", decide), Reject)  # not paired yet
    assert isinstance(run_op(table, "seat-1", PairTables(class_id, first, second)), Ok)
    assert isinstance(run_op(table, "seat-2", decide), Ok)
    other_table = SetClassDecision(class_id, second, "Defenses")
    assert isinstance(run_op(table, "seat-2", other_table), Reject)
    assert table.classes[class_id].decisions == {first: "Attack"}
