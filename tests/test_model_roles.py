"""The facilitator is an optional role any seat may take, one at a time."""

from __future__ import annotations

from _model_support import FACILITATOR, SEAT_A, SEAT_B, build_sample_table

from sandbox.model import (
    Ok,
    Reject,
    ReleaseFacilitator,
    Table,
    TakeFacilitator,
    facilitator_seat,
    run_op,
)


def _nobody_facilitates() -> Table:
    table = build_sample_table()
    table.seats[FACILITATOR].is_facilitator = False
    return table


def test_any_seat_may_take_the_role_when_nobody_has_it() -> None:
    table = _nobody_facilitates()
    assert isinstance(run_op(table, SEAT_A, TakeFacilitator()), Ok)
    assert facilitator_seat(table) == SEAT_A
    assert table.is_facilitator(SEAT_A)


def test_a_second_seat_cannot_take_it_while_it_is_held() -> None:
    table = _nobody_facilitates()
    run_op(table, SEAT_A, TakeFacilitator())
    refused = run_op(table, SEAT_B, TakeFacilitator())
    assert isinstance(refused, Reject) and "already the facilitator" in refused.reason


def test_only_the_holder_hands_it_back_and_then_anyone_may_take_it() -> None:
    table = _nobody_facilitates()
    run_op(table, SEAT_A, TakeFacilitator())
    assert isinstance(run_op(table, SEAT_B, ReleaseFacilitator()), Reject)
    assert isinstance(run_op(table, SEAT_A, ReleaseFacilitator()), Ok)
    assert facilitator_seat(table) is None
    assert isinstance(run_op(table, SEAT_B, TakeFacilitator()), Ok)
