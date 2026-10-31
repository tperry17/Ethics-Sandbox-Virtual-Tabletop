"""Value Cards Trading as an activity: the deal, swaps, the checklist, recording."""

from __future__ import annotations

from sandbox.games import GAMES
from sandbox.games.engine import (
    build_activity_start,
    build_macro,
    build_seat,
    build_table,
)
from sandbox.model import (
    AcceptSwap,
    JoinActivity,
    MoveToZone,
    OfferSwap,
    Ok,
    OpenActivity,
    Record,
    Reject,
    Table,
    TableRng,
    Transaction,
    run_op,
)

GAME = GAMES["value-cards-trading"]
PLAYERS = ("seat-1", "seat-2", "seat-3")


def _room() -> Table:
    """An open room with four people in it; the first three will play."""
    table = Table(rng=TableRng(seed=3))
    seat_id, transaction = build_table(None, table, participant_id="p-1")
    assert isinstance(run_op(table, seat_id, transaction), Ok)
    for person in range(2, 5):
        seat_id, transaction = build_seat(None, table, participant_id=f"p-{person}")
        assert isinstance(run_op(table, seat_id, transaction), Ok)
    return table


def _start(table: Table) -> str:
    meta = GAME.definition.meta
    opened = OpenActivity(
        kind=meta.slug,
        title=meta.title,
        min_players=meta.players.min,
        max_players=meta.players.max,
    )
    assert isinstance(run_op(table, PLAYERS[0], opened), Ok)
    activity_id = next(reversed(table.activities))
    for seat in PLAYERS[1:]:
        assert isinstance(run_op(table, seat, JoinActivity(activity_id)), Ok)
    built = build_activity_start(GAME, table, PLAYERS[0], activity_id)
    assert isinstance(built, Transaction), built
    assert isinstance(run_op(table, PLAYERS[0], built), Ok)
    return activity_id


def _press(table: Table, activity_id: str, macro: str, seat: str = "seat-1") -> object:
    built = build_macro(GAME, table, seat, macro, activity_id)
    if isinstance(built, Reject):
        return built
    return run_op(table, seat, built)


def _dealt() -> tuple[Table, str]:
    table = _room()
    activity_id = _start(table)
    assert isinstance(_press(table, activity_id, "deal"), Ok)
    return table, activity_id


def _hand(table: Table, activity_id: str, seat: str) -> list[str]:
    zone = f"{activity_id}:hand-{seat}"
    return [p.id for p in table.pieces_in_zone(zone)]


def test_it_takes_exactly_three_and_starts_when_the_third_signs_up() -> None:
    meta = GAME.definition.meta
    assert meta.players.min == meta.players.max == 3
    table = _room()
    activity_id = _start(table)
    assert table.activities[activity_id].seats == PLAYERS
    assert f"{activity_id}:hand-seat-4" not in table.zones


def test_deal_gives_twelve_open_cards_to_each_of_three() -> None:
    table, activity_id = _dealt()
    for seat in PLAYERS:
        zone = f"{activity_id}:hand-{seat}"
        hand = table.pieces_in_zone(zone)
        assert len(hand) == 12
        assert all(card.face_up for card in hand)
    assert not table.pieces_in_zone(f"{activity_id}:deck")


def test_each_player_has_a_top_three_zone_of_three() -> None:
    table, activity_id = _dealt()
    for seat in PLAYERS:
        zone = table.zones[f"{activity_id}:top-three-{seat}"]
        assert zone.capacity == 3 and zone.owner_seat == seat


def test_nobody_may_take_from_another_hand_but_a_trade_swaps() -> None:
    table, activity_id = _dealt()
    mine = _hand(table, activity_id, "seat-1")[0]
    theirs = _hand(table, activity_id, "seat-2")[0]
    taking = run_op(table, "seat-3", MoveToZone(piece_id=theirs, zone_id="table"))
    assert isinstance(taking, Reject)
    offer = OfferSwap(to_seat="seat-2", give=(mine,), want=(theirs,))
    assert isinstance(run_op(table, "seat-1", offer), Ok)
    assert isinstance(run_op(table, "seat-2", AcceptSwap(offer_id=offer.op_id)), Ok)
    assert mine in _hand(table, activity_id, "seat-2")
    assert theirs in _hand(table, activity_id, "seat-1")
    assert len(_hand(table, activity_id, "seat-1")) == 12


def test_the_top_three_zone_holds_three_and_is_not_shown_automatically() -> None:
    table, activity_id = _dealt()
    zone = f"{activity_id}:top-three-seat-1"
    for card in _hand(table, activity_id, "seat-1")[:3]:
        move = MoveToZone(piece_id=card, zone_id=zone)
        assert isinstance(run_op(table, "seat-1", move), Ok)
    fourth = MoveToZone(piece_id=_hand(table, activity_id, "seat-1")[0], zone_id=zone)
    assert isinstance(run_op(table, "seat-1", fourth), Reject)
    assert all(not p.revealed_to for p in table.pieces_in_zone(zone))


def test_recording_names_pairs_that_have_not_traded_and_trading_carries_on() -> None:
    table, activity_id = _dealt()
    mine = _hand(table, activity_id, "seat-1")[0]
    theirs = _hand(table, activity_id, "seat-2")[0]
    offer = OfferSwap(to_seat="seat-2", give=(mine,), want=(theirs,))
    run_op(table, "seat-1", offer)
    run_op(table, "seat-2", AcceptSwap(offer_id=offer.op_id))
    open_offer = OfferSwap(
        to_seat="seat-3",
        give=(_hand(table, activity_id, "seat-1")[1],),
        want=(_hand(table, activity_id, "seat-3")[0],),
    )
    run_op(table, "seat-1", open_offer)

    built = build_macro(GAME, table, "seat-3", "record_hands", activity_id)
    assert isinstance(built, Transaction)
    records = [step for step in built.steps if isinstance(step, Record)]
    assert records[0].data["not_yet_traded"] == [
        "Seat 1 and Seat 3",
        "Seat 2 and Seat 3",
    ]
    assert isinstance(run_op(table, "seat-3", built), Ok)
    # Nothing ended: the open offer is still open and can be answered.
    assert open_offer.op_id in table.offers
    accept = AcceptSwap(offer_id=open_offer.op_id)
    assert isinstance(run_op(table, "seat-3", accept), Ok)


def test_recording_before_the_deal_says_to_deal_first() -> None:
    table = _room()
    activity_id = _start(table)
    refused = _press(table, activity_id, "record_hands")
    assert isinstance(refused, Reject) and "Deal first" in refused.reason


def test_each_card_face_carries_its_group_and_its_schwartz_icon() -> None:
    cards = GAME.decks["values"]
    assert len(cards) == 36
    assert {card.face.group for card in cards} == {"Deck", "Sidebar"}
    for card in cards:
        assert card.face.image is not None
        assert card.face.badge is not None
        assert card.face.badge.startswith("/content/decks/value-cards/images/icons/")
        assert card.face.folio is not None
