"""The Value Cards Trading game: the deal, the swap through its table, call_time."""

from __future__ import annotations

from _games_support import press, seated

from sandbox.games import GAMES
from sandbox.games.engine import seat_zone_id
from sandbox.model import AcceptSwap, MoveToZone, OfferSwap, Ok, Record, Reject, run_op
from sandbox.model.entities import Table

GAME = GAMES["value-cards-trading"]


def _dealt() -> Table:
    table = seated(GAME, 3)
    assert isinstance(press(GAME, table, "deal"), Ok)
    return table


def _hand(table: Table, seat: str) -> list[str]:
    return [p.id for p in table.pieces_in_zone(seat_zone_id("hand", seat))]


def test_deal_gives_twelve_open_cards_to_each_of_three() -> None:
    table = _dealt()
    for seat in ("seat-1", "seat-2", "seat-3"):
        hand = table.pieces_in_zone(seat_zone_id("hand", seat))
        assert len(hand) == 12
        assert all(card.face_up for card in hand)
    assert not table.pieces_in_zone("deck")


def test_the_trio_has_exactly_three_seats_and_a_top_three_each() -> None:
    table = _dealt()
    assert GAME.definition.meta.players.min == GAME.definition.meta.players.max == 3
    for seat in ("seat-1", "seat-2", "seat-3"):
        zone = table.zones[seat_zone_id("top-three", seat)]
        assert zone.capacity == 3 and zone.owner_seat == seat


def test_nobody_may_take_from_another_hand_but_a_trade_swaps() -> None:
    table = _dealt()
    mine, theirs = _hand(table, "seat-1")[0], _hand(table, "seat-2")[0]
    # seat-1 is the room's facilitator, who may take any piece; seat-3 may not.
    taking = run_op(table, "seat-3", MoveToZone(piece_id=theirs, zone_id="table"))
    assert isinstance(taking, Reject)
    offer = OfferSwap(to_seat="seat-2", give=(mine,), want=(theirs,))
    assert isinstance(run_op(table, "seat-1", offer), Ok)
    assert isinstance(run_op(table, "seat-2", AcceptSwap(offer_id=offer.op_id)), Ok)
    assert mine in _hand(table, "seat-2") and theirs in _hand(table, "seat-1")
    assert len(_hand(table, "seat-1")) == len(_hand(table, "seat-2")) == 12


def test_the_top_three_zone_holds_three_and_is_not_shown_automatically() -> None:
    table = _dealt()
    zone = seat_zone_id("top-three", "seat-1")
    for card in _hand(table, "seat-1")[:3]:
        assert isinstance(
            run_op(table, "seat-1", MoveToZone(piece_id=card, zone_id=zone)), Ok
        )
    fourth = _hand(table, "seat-1")[0]
    assert isinstance(
        run_op(table, "seat-1", MoveToZone(piece_id=fourth, zone_id=zone)), Reject
    )
    assert all(not p.revealed_to for p in table.pieces_in_zone(zone))


def test_call_time_names_pairs_that_have_not_traded_and_never_blocks() -> None:
    table = _dealt()
    mine, theirs = _hand(table, "seat-1")[0], _hand(table, "seat-2")[0]
    offer = OfferSwap(to_seat="seat-2", give=(mine,), want=(theirs,))
    run_op(table, "seat-1", offer)
    run_op(table, "seat-2", AcceptSwap(offer_id=offer.op_id))
    pending = OfferSwap(
        to_seat="seat-3",
        give=(_hand(table, "seat-1")[1],),
        want=(_hand(table, "seat-3")[0],),
    )
    run_op(table, "seat-1", pending)
    built = press(GAME, table, "call_time", seat="seat-3")
    assert isinstance(built, Ok)
    assert not table.offers
    from sandbox.games.engine import build_macro

    transaction = build_macro(GAME, table, "seat-3", "call_time")
    records = [s for s in transaction.steps if isinstance(s, Record)]  # type: ignore[union-attr]
    assert records[0].data["not_yet_traded"] == [
        "First player and Third player",
        "Second player and Third player",
    ]


def test_call_time_before_the_deal_says_to_deal_first() -> None:
    table = seated(GAME, 3)
    refused = press(GAME, table, "call_time")
    assert isinstance(refused, Reject) and "Deal first" in refused.reason
