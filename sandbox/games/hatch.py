"""The Python escape hatch: what a game's ``rules.py`` may register.

Most of an exercise is data in its ``game.yaml``. When a mechanic cannot be
said as steps, the game's own ``rules.py`` registers a function for it:

- ``@macro("reveal")`` makes the function the body of the macro whose YAML
  says ``python: reveal``.
- ``@hook("after_setup")``, ``@hook("before_macro")`` and
  ``@hook("seat_change")`` run at those moments, inside the same
  transaction as whatever caused them.

Both kinds receive the table and a typed context and return the operations
to apply, in order. They are pure in the same way the model is: no I/O, no
global randomness, and no changing the table they are given (it is a copy,
so doing so changes nothing anyway). To refuse, raise ``MacroRefused`` with
a sentence a person can read; the whole macro is then refused with it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, TypeVar

from sandbox.model import Operation, Table

Moment = Literal["after_setup", "before_macro", "seat_change"]
MOMENTS: tuple[Moment, ...] = ("after_setup", "before_macro", "seat_change")


class MacroRefused(Exception):  # noqa: N818 - it is an answer, not a failure
    """Raised by a macro or hook to refuse, with a reason a person can read."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class GameContext:
    """What a macro or hook is told about the moment it runs in.

    ``seats`` is every seat at the table in seat order (an activity's own
    players, for an activity), and ``zone`` turns a
    zone's definition id into the zone on this table: the zone itself, or
    for a per-seat zone, the copy belonging to ``seat``.
    """

    actor_seat: str
    seats: tuple[str, ...]
    per_seat_zones: frozenset[str]
    macro_id: str | None = None
    seat_id: str | None = None
    prefix: str = ""

    def zone(self, zone_id: str, seat: str | None = None) -> str:
        if zone_id in self.per_seat_zones:
            if seat is None:
                raise ValueError(f"{zone_id!r} is a per-seat zone; name the seat")
            return f"{self.prefix}{zone_id}-{seat}"
        return f"{self.prefix}{zone_id}"

    def seat_zones(self, zone_id: str) -> tuple[str, ...]:
        """Every seat's copy of a per-seat zone, in seat order."""
        return tuple(self.zone(zone_id, seat) for seat in self.seats)


GameFunction = Callable[[Table, GameContext], Sequence[Operation]]
_F = TypeVar("_F", bound=GameFunction)

MACRO_ATTRIBUTE = "__sandbox_macro__"
HOOK_ATTRIBUTE = "__sandbox_hook__"


def macro(macro_id: str) -> Callable[[_F], _F]:
    """Register the decorated function as the body of macro ``macro_id``."""

    def register(function: _F) -> _F:
        setattr(function, MACRO_ATTRIBUTE, macro_id)
        return function

    return register


def hook(moment: Moment) -> Callable[[_F], _F]:
    """Register the decorated function to run at ``moment``."""
    if moment not in MOMENTS:
        raise ValueError(f"There is no hook moment {moment!r}.")

    def register(function: _F) -> _F:
        setattr(function, HOOK_ATTRIBUTE, moment)
        return function

    return register


__all__ = [
    "GameContext",
    "GameFunction",
    "HOOK_ATTRIBUTE",
    "MACRO_ATTRIBUTE",
    "MOMENTS",
    "MacroRefused",
    "Moment",
    "hook",
    "macro",
]
