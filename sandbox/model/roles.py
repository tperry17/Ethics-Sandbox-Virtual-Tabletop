"""The facilitator, an optional admin role that any seat may take.

Nobody holds it by default. A seat takes it when no one has it, and hands
it back when it is done; only one seat holds it at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sandbox.model.entities import Table
from sandbox.model.ops import new_op_id
from sandbox.model.results import Patch


def facilitator_seat(table: Table) -> str | None:
    """The seat holding the facilitator role, if anyone does."""
    return next((s.id for s in table.seats.values() if s.is_facilitator), None)


def _patch(seat_id: str, held: bool) -> Patch:
    return Patch(
        kind="seat",
        op="upsert",
        entity_id=seat_id,
        fields={"is_facilitator": held},
    )


@dataclass(frozen=True)
class TakeFacilitator:
    """Become the facilitator, if no one is."""

    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if actor_seat not in table.seats:
            return "Sit at the table to become the facilitator."
        holder = facilitator_seat(table)
        if holder == actor_seat:
            return "You are already the facilitator."
        if holder is not None:
            return f"{table.seats[holder].label} is already the facilitator."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        table.seats[actor_seat].is_facilitator = True
        return [_patch(actor_seat, True)]


@dataclass(frozen=True)
class ReleaseFacilitator:
    """Hand the facilitator role back, so anyone may take it."""

    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if not table.is_facilitator(actor_seat):
            return "You are not the facilitator."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        table.seats[actor_seat].is_facilitator = False
        return [_patch(actor_seat, False)]
