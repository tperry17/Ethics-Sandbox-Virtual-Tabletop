"""Swaps between two seats, and zones only their owner arranges."""

from __future__ import annotations

from _model_support import (
    FACILITATOR,
    HAND_A,
    HAND_B,
    SEAT_A,
    SEAT_B,
    build_sample_table,
)

from sandbox.model import (
    AcceptSwap,
    DeclineSwap,
    MoveToZone,
    OfferSwap,
    Ok,
    Piece,
    PieceKind,
    Reject,
    ResetTable,
    Table,
    Visibility,
    WithdrawSwap,
    project,
    run_op,
)


def _trading_table() -> Table:
    """Two open hands, two cards in each."""
    table = build_sample_table()
    for zone_id, seat in ((HAND_A, SEAT_A), (HAND_B, SEAT_B)):
        table.zones[zone_id].visibility = Visibility.PUBLIC
        table.zones[zone_id].owner_moves_only = True
        for index in range(2):
            piece_id = f"{seat}-{index}"
            table.pieces[piece_id] = Piece(
                id=piece_id,
                kind=PieceKind.CARD,
                component_id=f"value-{piece_id}",
                zone_id=zone_id,
                x=index * 10.0,
                y=0,
                z=index,
            )
    return table


def _reason(table: Table, seat: str, op: object) -> str:
    outcome = run_op(table, seat, op)  # type: ignore[arg-type]
    assert isinstance(outcome, Reject), outcome
    return outcome.reason


def test_an_open_hand_is_read_by_all_but_moved_only_by_its_owner() -> None:
    table = _trading_table()
    seen = project(table, SEAT_B)
    assert all(p.component_id for p in seen.pieces if p.zone_id == HAND_A)
    assert "someone else's hand" in _reason(
        table, SEAT_B, MoveToZone(piece_id="seat-a-0", zone_id="table")
    )
    assert "Only its owner" in _reason(
        table, SEAT_B, MoveToZone(piece_id="seat-b-0", zone_id=HAND_A)
    )
    assert isinstance(
        run_op(table, SEAT_A, MoveToZone(piece_id="seat-a-0", zone_id="table")), Ok
    )
    assert isinstance(
        run_op(table, FACILITATOR, MoveToZone(piece_id="seat-b-0", zone_id="table")),
        Ok,
    )


def test_an_accepted_offer_swaps_the_cards_at_once() -> None:
    table = _trading_table()
    offer = OfferSwap(to_seat=SEAT_B, give=("seat-a-0",), want=("seat-b-1",))
    assert isinstance(run_op(table, SEAT_A, offer), Ok)
    assert offer.op_id in table.offers
    assert table.pieces["seat-a-0"].zone_id == HAND_A  # nothing moves yet
    outcome = run_op(table, SEAT_B, AcceptSwap(offer_id=offer.op_id))
    assert isinstance(outcome, Ok)
    assert table.pieces["seat-a-0"].zone_id == HAND_B
    assert table.pieces["seat-b-1"].zone_id == HAND_A
    assert not table.offers
    assert frozenset((SEAT_A, SEAT_B)) in table.swapped
    assert len(project(table, SEAT_A).swapped) == 1


def test_unequal_counts_and_gifts_and_taking_are_refused() -> None:
    table = _trading_table()
    unequal = OfferSwap(
        to_seat=SEAT_B, give=("seat-a-0",), want=("seat-b-0", "seat-b-1")
    )
    assert "same number" in _reason(table, SEAT_A, unequal)
    gift = OfferSwap(to_seat=SEAT_B, give=("seat-a-0",), want=())
    assert "exchange" in _reason(table, SEAT_A, gift)
    taking = OfferSwap(to_seat=SEAT_B, give=(), want=("seat-b-0",))
    assert "without giving" in _reason(table, SEAT_A, taking)
    assert not table.offers


def test_an_offer_must_name_the_right_hands() -> None:
    table = _trading_table()
    other = OfferSwap(to_seat=SEAT_B, give=("seat-b-0",), want=("seat-b-1",))
    assert "your own hand" in _reason(table, SEAT_A, other)
    wrong = OfferSwap(to_seat=SEAT_B, give=("seat-a-0",), want=("seat-a-1",))
    assert "hand" in _reason(table, SEAT_A, wrong)
    assert "yourself" in _reason(
        table, SEAT_A, OfferSwap(to_seat=SEAT_A, give=("seat-a-0",), want=("seat-a-1",))
    )


def test_only_the_recipient_answers_and_only_the_maker_withdraws() -> None:
    table = _trading_table()
    offer = OfferSwap(to_seat=SEAT_B, give=("seat-a-0",), want=("seat-b-0",))
    run_op(table, SEAT_A, offer)
    assert "made to" in _reason(table, SEAT_A, AcceptSwap(offer_id=offer.op_id))
    assert "made to" in _reason(table, SEAT_A, DeclineSwap(offer_id=offer.op_id))
    assert "made this offer" in _reason(
        table, SEAT_B, WithdrawSwap(offer_id=offer.op_id)
    )
    assert isinstance(run_op(table, SEAT_A, WithdrawSwap(offer_id=offer.op_id)), Ok)
    assert "already been answered" in _reason(
        table, SEAT_B, AcceptSwap(offer_id=offer.op_id)
    )


def test_a_declined_offer_moves_nothing_and_is_not_a_completed_pair() -> None:
    table = _trading_table()
    offer = OfferSwap(to_seat=SEAT_B, give=("seat-a-0",), want=("seat-b-0",))
    run_op(table, SEAT_A, offer)
    assert isinstance(run_op(table, SEAT_B, DeclineSwap(offer_id=offer.op_id)), Ok)
    assert table.pieces["seat-a-0"].zone_id == HAND_A
    assert not table.swapped


def test_a_card_in_an_open_offer_cannot_be_offered_again() -> None:
    table = _trading_table()
    run_op(
        table,
        SEAT_A,
        OfferSwap(to_seat=SEAT_B, give=("seat-a-0",), want=("seat-b-0",)),
    )
    again = OfferSwap(to_seat=SEAT_B, give=("seat-a-0",), want=("seat-b-1",))
    assert "already in another" in _reason(table, SEAT_A, again)


def test_an_offer_goes_stale_if_a_card_moved() -> None:
    table = _trading_table()
    offer = OfferSwap(to_seat=SEAT_B, give=("seat-a-0",), want=("seat-b-0",))
    run_op(table, SEAT_A, offer)
    run_op(table, SEAT_A, MoveToZone(piece_id="seat-a-0", zone_id="table"))
    assert "moved since" in _reason(table, SEAT_B, AcceptSwap(offer_id=offer.op_id))


def test_resetting_the_table_clears_offers_and_the_checklist() -> None:
    table = _trading_table()
    run_op(
        table, SEAT_A, OfferSwap(to_seat=SEAT_B, give=("seat-a-0",), want=("seat-b-0",))
    )
    table.swapped.add(frozenset((SEAT_A, SEAT_B)))
    assert isinstance(run_op(table, FACILITATOR, ResetTable()), Ok)
    assert not table.offers and not table.swapped
