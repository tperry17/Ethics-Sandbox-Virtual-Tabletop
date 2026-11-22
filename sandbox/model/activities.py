"""Activities: guided exercises started inside a room for some of its seats.

An activity is opened, signed up to, and begun; beginning lays out its
zones (a transaction built by the game layer, which knows the definition).
Ending it removes those zones and what is in them. Nothing here knows what
any activity is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sandbox.model.entities import SYSTEM_SEAT, Activity, Table
from sandbox.model.ops import new_op_id
from sandbox.model.results import Patch


def _patch(activity: Activity) -> Patch:
    return Patch(
        kind="activity",
        op="upsert",
        entity_id=activity.id,
        fields={
            "kind": activity.kind,
            "title": activity.title,
            "min_players": activity.min_players,
            "max_players": activity.max_players,
            "seats": list(activity.seats),
            "status": activity.status,
            "zones": list(activity.zones),
            "options": dict(activity.options),
        },
    )


def _removed(activity_id: str) -> Patch:
    return Patch(kind="activity", op="remove", entity_id=activity_id, fields={})


def _reason_missing(table: Table, activity_id: str) -> str | None:
    if activity_id not in table.activities:
        return "That activity is not running any more."
    return None


@dataclass(frozen=True)
class OpenActivity:
    """Open a sign-up for an activity. The opener is the first to sign up."""

    kind: str
    title: str
    min_players: int
    max_players: int
    options: tuple[tuple[str, str], ...] = ()
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if actor_seat not in table.seats:
            return "Sit at the table to start an activity."
        if self.min_players < 1 or self.max_players < self.min_players:
            return "That activity has no sensible number of players."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        table.activity_serial += 1
        activity = Activity(
            id=f"activity-{table.activity_serial}",
            kind=self.kind,
            title=self.title,
            min_players=self.min_players,
            max_players=self.max_players,
            seats=(actor_seat,),
            options=dict(self.options),
        )
        table.activities[activity.id] = activity
        return [_patch(activity)]


@dataclass(frozen=True)
class JoinActivity:
    """Sign up for an activity that has not begun."""

    activity_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.activity_id)) is not None:
            return reason
        activity = table.activities[self.activity_id]
        if activity.status != "signup":
            return "That activity has already begun."
        if actor_seat in activity.seats:
            return "You have already signed up."
        if len(activity.seats) >= activity.max_players:
            return "That activity is full."
        if activity.class_id and table.is_facilitator(actor_seat):
            return "The facilitator runs a class and does not sit at a table."
        if activity.class_id and any(
            actor_seat in table.activities[other].seats
            for other in table.classes[activity.class_id].tables
            if other in table.activities
        ):
            return "You already have a table in this class. Leave it first."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        activity = table.activities[self.activity_id]
        activity.seats = (*activity.seats, actor_seat)
        return [_patch(activity)]


@dataclass(frozen=True)
class JoinRunningActivity:
    """Join an activity that has already begun, while it has room.

    ``seat_id`` is who joins: themselves, or anyone when the room acts for
    them inside the transaction that lays out their zones. ``added_zones``
    are the zones the game layer has just made for the new player, in the
    same transaction. A table of a class is joined through the
    facilitator's moves instead.
    """

    activity_id: str
    seat_id: str
    added_zones: tuple[str, ...] = ()
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.activity_id)) is not None:
            return reason
        if actor_seat not in (self.seat_id, SYSTEM_SEAT):
            return "You can only join an activity yourself."
        activity = table.activities[self.activity_id]
        if activity.status != "running":
            return "That activity has not begun. Sign up instead."
        if activity.class_id:
            return "A table of a class is joined when the facilitator moves you there."
        if self.seat_id in activity.seats:
            return "You are already playing."
        if len(activity.seats) >= activity.max_players:
            return "That activity is full."
        if self.seat_id not in table.seats:
            return "Take a seat at the table first."
        for zone_id in self.added_zones:
            if zone_id not in table.zones:
                return f"There is no zone {zone_id!r} on the table."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        activity = table.activities[self.activity_id]
        activity.seats = (*activity.seats, self.seat_id)
        activity.zones = (*activity.zones, *self.added_zones)
        return [_patch(activity)]


@dataclass(frozen=True)
class LeaveActivity:
    """Take your name off an activity that has not begun.

    Leaving is not cancelling: the sign-up stays open for others even when
    the last name comes off it. Cancelling is ``EndActivity``.
    """

    activity_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.activity_id)) is not None:
            return reason
        activity = table.activities[self.activity_id]
        if activity.status != "signup":
            return "That activity has already begun. End it instead."
        if actor_seat not in activity.seats:
            return "You are not signed up for that activity."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        activity = table.activities[self.activity_id]
        activity.seats = tuple(seat for seat in activity.seats if seat != actor_seat)
        return [_patch(activity)]


@dataclass(frozen=True)
class SetActivityPlayers:
    """The facilitator chooses who plays, instead of the sign-up."""

    activity_id: str
    seats: tuple[str, ...]
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.activity_id)) is not None:
            return reason
        activity = table.activities[self.activity_id]
        if not table.is_facilitator(actor_seat):
            return "Only the facilitator can choose the players."
        if activity.status != "signup":
            return "That activity has already begun."
        if len(set(self.seats)) != len(self.seats):
            return "A player can be chosen only once."
        if any(seat not in table.seats for seat in self.seats):
            return "Choose people who are at the table."
        if not activity.min_players <= len(self.seats) <= activity.max_players:
            return (
                f"{activity.title} takes {activity.min_players}"
                f"–{activity.max_players} players."
            )
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        activity = table.activities[self.activity_id]
        activity.seats = self.seats
        return [_patch(activity)]


@dataclass(frozen=True)
class BeginActivity:
    """Mark an activity running, once the game layer has laid out its ``zones``."""

    activity_id: str
    zones: tuple[str, ...]
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.activity_id)) is not None:
            return reason
        activity = table.activities[self.activity_id]
        if activity.status != "signup":
            return "That activity has already begun."
        if not activity.min_players <= len(activity.seats) <= activity.max_players:
            return (
                f"{activity.title} needs {activity.min_players}"
                f"–{activity.max_players} players; "
                f"{len(activity.seats)} have signed up."
            )
        if actor_seat not in activity.seats and not table.is_facilitator(actor_seat):
            return "Only a player or the facilitator can begin it."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        activity = table.activities[self.activity_id]
        activity.status = "running"
        activity.zones = self.zones
        return [_patch(activity)]


@dataclass(frozen=True)
class EndActivity:
    """End an activity: its zones and everything in them leave the table."""

    activity_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.activity_id)) is not None:
            return reason
        activity = table.activities[self.activity_id]
        if activity.class_id and not table.is_facilitator(actor_seat):
            return "Only the facilitator can end a table of a class."
        # A sign-up nobody is in any more belongs to nobody: anyone may cancel it.
        unclaimed = activity.status == "signup" and not activity.seats
        if (
            actor_seat not in activity.seats
            and not table.is_facilitator(actor_seat)
            and not unclaimed
        ):
            return "Only its players or the facilitator can end it."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        activity = table.activities.pop(self.activity_id)
        group = table.classes.get(activity.class_id)
        if group is not None:
            group.tables = tuple(t for t in group.tables if t != activity.id)
            group.pairs = tuple(p for p in group.pairs if activity.id not in p)
            group.decisions.pop(activity.id, None)
            group.proposed.pop(activity.id, None)
        patches: list[Patch] = []
        for zone_id in activity.zones:
            for piece in table.pieces_in_zone(zone_id):
                del table.pieces[piece.id]
                patches.append(
                    Patch(kind="piece", op="remove", entity_id=piece.id, fields={})
                )
            if table.zones.pop(zone_id, None) is not None:
                patches.append(
                    Patch(kind="zone", op="remove", entity_id=zone_id, fields={})
                )
        patches.append(_removed(activity.id))
        return patches
