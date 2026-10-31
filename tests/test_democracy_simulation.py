"""The Democracy Simulation: dealing, the co-Chairs, and counting a vote."""

from __future__ import annotations

from collections import Counter

import pytest

from sandbox.content_loading import CONTENT_ROOT
from sandbox.games import GAMES
from sandbox.games.democracy_simulation.compose import files
from sandbox.games.engine import (
    build_activity_start,
    build_macro,
    build_seat,
    build_table,
    seat_order,
)
from sandbox.model import (
    MoveToZone,
    Ok,
    OpenActivity,
    OpOutcome,
    Reject,
    SetActivityPlayers,
    Table,
    TableRng,
    TakeFacilitator,
    Transaction,
    project,
    run_op,
)

GAME = GAMES["democracy-simulation"]


def city(
    people: int, *, city: str = "potamosia", phase: str = "1", seed: int = 3
) -> tuple[Table, str]:
    """A room with a running activity of ``people`` players. Returns table, id."""
    table = Table(rng=TableRng(seed=seed))
    seat, tx = build_table(None, table, participant_id="p-1")
    assert isinstance(run_op(table, seat, tx), Ok)
    for person in range(2, people + 1):
        seat, tx = build_seat(None, table, participant_id=f"p-{person}")
        assert isinstance(run_op(table, seat, tx), Ok)
    opened = OpenActivity(
        "democracy-simulation",
        GAME.title,
        9,
        20,
        options=(("city", city), ("phase", phase)),
    )
    assert isinstance(run_op(table, "seat-1", opened), Ok)
    activity_id = next(iter(table.activities))
    seats = seat_order(table)
    assert isinstance(
        run_op(table, "seat-1", SetActivityPlayers(activity_id, seats)), Reject
    )  # only the facilitator chooses players
    assert isinstance(run_op(table, "seat-1", TakeFacilitator()), Ok)
    assert isinstance(
        run_op(table, "seat-1", SetActivityPlayers(activity_id, seats)), Ok
    )
    built = build_activity_start(GAME, table, "seat-1", activity_id)
    assert isinstance(built, Transaction)
    assert isinstance(run_op(table, "seat-1", built), Ok)
    return table, activity_id


def press(table: Table, activity: str, macro: str, seat: str = "seat-1") -> OpOutcome:
    built = build_macro(GAME, table, seat, macro, activity)
    if isinstance(built, Reject):
        return built
    return run_op(table, seat, built)


def zone(activity: str, name: str, seat: str | None = None) -> str:
    return f"{activity}:{name}" + ("" if seat is None else f"-{seat}")


def components(table: Table, zone_id: str) -> list[str]:
    return [p.component_id for p in table.pieces_in_zone(zone_id)]


def role_numbers(table: Table, activity: str) -> list[int]:
    cards = GAME.cards()
    numbers = []
    for seat in table.activities[activity].seats:
        held = [
            p.component_id
            for p in table.pieces_in_zone(zone(activity, "hand", seat))
            if cards[p.component_id]["kind"] == "role"
        ]
        assert len(held) == 1
        numbers.append(int(cards[held[0]]["card_number"]))
    return numbers


def test_the_card_files_are_up_to_date() -> None:
    for path, text in files().items():
        written = (CONTENT_ROOT / "exercises/democracy-simulation" / path).read_text(
            encoding="utf-8"
        )
        assert written == text, (
            f"{path} is out of date: run "
            "`uv run python sandbox/games/democracy_simulation/compose.py`"
        )


@pytest.mark.parametrize("people", [9, 14, 20])
@pytest.mark.parametrize("which", ["potamosia", "hudrosia"])
def test_deal_gives_cards_one_to_n(people: int, which: str) -> None:
    table, activity = city(people, city=which)
    assert isinstance(press(table, activity, "deal"), Ok)
    assert sorted(role_numbers(table, activity)) == list(range(1, people + 1))
    cards = GAME.cards()
    for seat in table.activities[activity].seats:
        hand = table.pieces_in_zone(zone(activity, "hand", seat))
        role = next(p for p in hand if cards[p.component_id]["kind"] == "role")
        sheets = [p for p in hand if cards[p.component_id]["kind"] == "sheet"]
        number = cards[role.component_id]["card_number"]
        # Elite cards, and only they, come with their own sheet.
        assert len(sheets) == (
            1
            if any(
                cards[c]["card_number"] == number and cards[c]["kind"] == "sheet"
                for c in cards
                if cards[c]["city"].lower() == which and cards[c]["phase"] == "1"
            )
            else 0
        )
        tents = components(table, zone(activity, "tent", seat)) + components(
            table, zone(activity, "council")
        )
        assert f"tent-{cards[role.component_id]['job'].lower()}" in tents


def test_a_redeal_is_allowed_until_the_meeting_starts() -> None:
    table, activity = city(9)
    assert isinstance(press(table, activity, "deal"), Ok)
    assert isinstance(press(table, activity, "deal"), Ok)
    assert sorted(role_numbers(table, activity)) == list(range(1, 10))
    assert isinstance(press(table, activity, "start_meeting"), Ok)
    refused = press(table, activity, "deal")
    assert isinstance(refused, Reject) and "started" in refused.reason


def test_no_card_back_or_sheet_can_be_shown() -> None:
    table, activity = city(9)
    press(table, activity, "deal")
    from sandbox.model import ShowTo

    cards = GAME.cards()
    for piece in table.pieces.values():
        if cards.get(piece.component_id, {}).get("kind") in {"role", "sheet"}:
            assert piece.props.get("revealable") is False
            assert ShowTo(piece_id=piece.id).validate(table, "seat-1") is not None


def test_hudrosia_has_a_council_zone_and_potamosia_does_not() -> None:
    hud, h = city(9, city="hudrosia")
    pot, p = city(9)
    assert zone(h, "council") in hud.zones
    assert zone(p, "council") not in pot.zones


def test_two_co_chairs_are_chosen_in_potamosia_only() -> None:
    table, activity = city(12)
    refused = press(table, activity, "choose_moderators")
    assert isinstance(refused, Reject) and "Deal" in refused.reason
    press(table, activity, "deal")
    assert isinstance(press(table, activity, "choose_moderators"), Ok)
    holders = [
        seat
        for seat in table.activities[activity].seats
        if "moderator-token" in components(table, zone(activity, "tent", seat))
    ]
    assert len(holders) == 2
    assert not table.pieces_in_zone(zone(activity, "lots"))
    again = press(table, activity, "choose_moderators")
    assert isinstance(again, Reject)
    hud, h = city(9, city="hudrosia")
    press(hud, h, "deal")
    assert isinstance(press(hud, h, "choose_moderators"), Reject)


def test_the_same_seed_chooses_the_same_co_chairs() -> None:
    def chosen(seed: int) -> list[str]:
        table, activity = city(12, seed=seed)
        press(table, activity, "deal")
        press(table, activity, "choose_moderators")
        return [
            s
            for s in table.activities[activity].seats
            if "moderator-token" in components(table, zone(activity, "tent", s))
        ]

    assert chosen(5) == chosen(5)
    assert any(chosen(5) != chosen(seed) for seed in range(6, 14))


def _vote(table: Table, activity: str, choices: dict[str, str]) -> None:
    """Each seat moves its own token for ``choices[seat]`` into its slot."""
    for seat, value in choices.items():
        box = table.pieces_in_zone(zone(activity, "ballot-box", seat))
        token = next(p for p in box if p.component_id == value)
        moved = MoveToZone(piece_id=token.id, zone_id=zone(activity, "ballot", seat))
        assert isinstance(run_op(table, seat, moved), Ok)


def _open_vote(table: Table, activity: str) -> None:
    assert isinstance(press(table, activity, "new_proposal", "seat-2"), Ok)
    assert isinstance(press(table, activity, "put_to_vote"), Ok)


def test_a_majority_passes_and_every_seat_has_a_ballot_in_potamosia() -> None:
    table, activity = city(9)
    press(table, activity, "deal")
    _open_vote(table, activity)
    seats = table.activities[activity].seats
    assert all(
        sorted(components(table, zone(activity, "ballot-box", s))) == ["no", "yes"]
        for s in seats
    )
    _vote(table, activity, {s: "yes" if i < 5 else "no" for i, s in enumerate(seats)})
    assert isinstance(press(table, activity, "close_vote"), Ok)
    assert components(table, zone(activity, "passed")) == ["proposal"]
    assert Counter(components(table, zone(activity, "tally-yes"))) == {"yes": 5}
    assert Counter(components(table, zone(activity, "tally-no"))) == {"no": 4}
    assert "result-passed" in components(table, zone(activity, "floor"))
    # A show of hands: each vote is turned up in its voter's name tent, for all.
    spectator = project(table, None)
    shown = {
        p.zone_id: p.component_id
        for p in spectator.pieces
        if p.component_id in ("yes", "no")
    }
    assert shown[zone(activity, "tent", seats[0])] == "yes"
    assert shown[zone(activity, "tent", seats[8])] == "no"


def test_more_than_half_of_the_votes_cast_not_of_those_present() -> None:
    table, activity = city(9)
    press(table, activity, "deal")
    _open_vote(table, activity)
    seats = table.activities[activity].seats
    _vote(table, activity, {seats[0]: "yes", seats[1]: "yes", seats[2]: "no"})
    assert isinstance(press(table, activity, "close_vote"), Ok)
    assert components(table, zone(activity, "passed")) == ["proposal"]


def test_a_minority_does_not_pass() -> None:
    table, activity = city(9)
    press(table, activity, "deal")
    _open_vote(table, activity)
    seats = table.activities[activity].seats
    _vote(table, activity, {seats[0]: "yes", seats[1]: "no", seats[2]: "no"})
    press(table, activity, "close_vote")
    assert components(table, zone(activity, "not-passed")) == ["proposal"]
    assert "result-not-passed" in components(table, zone(activity, "floor"))


def test_a_tie_is_reported_and_nothing_passes() -> None:
    table, activity = city(9)
    press(table, activity, "deal")
    _open_vote(table, activity)
    seats = table.activities[activity].seats
    _vote(table, activity, {seats[0]: "yes", seats[1]: "no"})
    assert isinstance(press(table, activity, "close_vote"), Ok)
    assert "result-tie" in components(table, zone(activity, "floor"))
    assert not components(table, zone(activity, "passed"))
    assert components(table, zone(activity, "proposals")) == ["proposal"]


def test_nobody_voting_is_refused_and_leaves_the_vote_open() -> None:
    table, activity = city(9)
    press(table, activity, "deal")
    _open_vote(table, activity)
    refused = press(table, activity, "close_vote")
    assert isinstance(refused, Reject) and "Nobody has voted" in refused.reason
    assert "vote-open" in components(table, zone(activity, "floor"))


def test_only_a_co_chair_or_the_facilitator_can_call_a_vote_in_potamosia() -> None:
    table, activity = city(12)
    press(table, activity, "deal")
    press(table, activity, "choose_moderators")
    press(table, activity, "new_proposal", "seat-2")
    seats = table.activities[activity].seats
    chair = next(
        s
        for s in seats
        if "moderator-token" in components(table, zone(activity, "tent", s))
    )
    other = next(s for s in seats if s != chair and s != "seat-1")
    # The facilitator has the seat only by role; take it away to test the rest.
    from sandbox.model import ReleaseFacilitator

    assert isinstance(run_op(table, "seat-1", ReleaseFacilitator()), Ok)
    assert isinstance(press(table, activity, "put_to_vote", other), Reject)
    assert isinstance(press(table, activity, "put_to_vote", chair), Ok)


def test_hudrosia_only_the_council_votes_and_a_king_calls_it() -> None:
    table, activity = city(12, city="hudrosia")
    press(table, activity, "deal")
    cards = GAME.cards()
    seats = table.activities[activity].seats

    def role(seat: str) -> dict[str, str]:
        for p in table.pieces_in_zone(zone(activity, "hand", seat)):
            if cards[p.component_id]["kind"] == "role":
                return cards[p.component_id]
        raise AssertionError

    council = [s for s in seats if role(s)["council"] == "yes"]
    others = [s for s in seats if s not in council]
    king = next(s for s in seats if role(s)["job"] == "King")
    from sandbox.model import ReleaseFacilitator

    press(table, activity, "new_proposal", others[0])
    assert isinstance(run_op(table, "seat-1", ReleaseFacilitator()), Ok)
    assert isinstance(press(table, activity, "put_to_vote", others[0]), Reject)
    assert isinstance(press(table, activity, "put_to_vote", king), Ok)
    for seat in others:
        assert not table.pieces_in_zone(zone(activity, "ballot-box", seat))
    for seat in council:
        assert len(table.pieces_in_zone(zone(activity, "ballot-box", seat))) == 2


def test_a_secret_council_vote_does_not_leak_to_the_table() -> None:
    table, activity = city(12, city="hudrosia")
    press(table, activity, "deal")
    cards = GAME.cards()
    seats = table.activities[activity].seats
    council = [
        s
        for s in seats
        if any(
            cards[p.component_id]["council"] == "yes"
            for p in table.pieces_in_zone(zone(activity, "hand", s))
            if cards[p.component_id]["kind"] == "role"
        )
    ]
    assert len(council) >= 3
    _open_vote(table, activity)
    choices = {s: ("yes" if i % 2 == 0 else "no") for i, s in enumerate(council)}
    _vote(table, activity, choices)
    # While it is open, only a seat and the facilitator can read a ballot.
    others = [s for s in seats if s != council[0] and s != "seat-1"]
    for viewer in (others[0], None):
        view = project(table, viewer)
        slot = zone(activity, "ballot", council[0])
        assert all(p.component_id is None for p in view.pieces if p.zone_id == slot)
    assert any(
        p.component_id == choices[council[0]]
        for p in project(table, council[0]).pieces
        if p.zone_id == zone(activity, "ballot", council[0])
    )
    assert isinstance(press(table, activity, "close_vote"), Ok)
    yes = sum(v == "yes" for v in choices.values())
    for viewer in (others[0], council[0], None):
        view = project(table, viewer)
        yes_tally = [p for p in view.pieces if p.zone_id == zone(activity, "tally-yes")]
        assert len(yes_tally) == yes
        # Nothing marks a voter's choice: no token anywhere but the tally is
        # a yes or a no, and the council members' own slots and tents are bare.
        for s in council:
            for z in ("tent", "ballot", "ballot-box"):
                visible = [
                    p.component_id
                    for p in view.pieces
                    if p.zone_id == zone(activity, z, s)
                    and p.component_id in ("yes", "no")
                ]
                assert visible == []


def test_the_log_keeps_who_voted_what_for_the_facilitator() -> None:
    table, activity = city(9)
    press(table, activity, "deal")
    _open_vote(table, activity)
    seats = table.activities[activity].seats
    _vote(table, activity, {seats[0]: "yes", seats[1]: "no"})
    built = build_macro(GAME, table, "seat-1", "close_vote", activity)
    assert isinstance(built, Transaction)
    records = [s for s in built.steps if type(s).__name__ == "Record"]
    assert records and records[-1].data["votes"] == {  # type: ignore[attr-defined]
        table.seats[seats[0]].label: "yes",
        table.seats[seats[1]].label: "no",
    }


def test_start_meeting_records_every_seats_card_and_interest() -> None:
    table, activity = city(9)
    press(table, activity, "deal")
    built = build_macro(GAME, table, "seat-1", "start_meeting", activity)
    assert isinstance(built, Transaction)
    record = next(s for s in built.steps if type(s).__name__ == "Record")
    seats = record.data["seats"]  # type: ignore[attr-defined]
    assert len(seats) == 9
    assert all({"card_number", "job", "interest"} <= set(v) for v in seats.values())
    assert all(v["interest"] for v in seats.values())
