"""Classes: one activity run as several tables at once, by the facilitator.

A class starts the same activity at a number of tables in one room. Its
tables are ordinary activities, so everything that works for an activity
works for a table of a class; the class adds what only the facilitator
needs: sorting people into tables, one timer and one pushed prompt for
every table, and pairing two tables. Nothing here knows what any activity
is, or what a decision means.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sandbox.model.activities import EndActivity
from sandbox.model.entities import Activity, ClassGroup, Table
from sandbox.model.ops import new_op_id
from sandbox.model.results import Patch
from sandbox.model.rng import TableRng

MAX_TABLES = 15
MAX_TIMER_SECONDS = 3 * 60 * 60


def sort_into_tables(
    people: list[str], limits: list[tuple[int, int]], rng: TableRng
) -> list[tuple[str, ...]] | str:
    """Deal ``people`` into tables at random, as evenly as each table's range allows.

    ``limits`` is each table's (minimum, maximum) number of players. Returns
    one tuple of people per table, or a sentence saying why it cannot be
    done. It draws from the table's own generator, so the result is
    reproducible from the log.
    """
    count = len(people)
    if not limits:
        return "There are no tables."
    if count > sum(high for _, high in limits):
        return "There are more people than seats at these tables."
    if count < sum(low for low, _ in limits):
        return "There are too few people to fill every table to its minimum."
    order = [people[i] for i in rng.shuffled_indices(count)]
    sizes = [low for low, _ in limits]
    left = count - sum(sizes)
    # Hand out the rest one at a time to the emptiest table with room.
    while left > 0:
        open_tables = [i for i, (_, high) in enumerate(limits) if sizes[i] < high]
        emptiest = min(open_tables, key=lambda i: (sizes[i], i))
        sizes[emptiest] += 1
        left -= 1
    tables: list[tuple[str, ...]] = []
    start = 0
    for size in sizes:
        tables.append(tuple(order[start : start + size]))
        start += size
    return tables


def _class_patch(group: ClassGroup) -> Patch:
    return Patch(
        kind="table",
        op="event",
        entity_id=group.id,
        fields={"type": "class", "tables": list(group.tables)},
    )


def _reason_missing(table: Table, class_id: str) -> str | None:
    if class_id not in table.classes:
        return "That class is not running any more."
    return None


def _facilitator_only(table: Table, actor_seat: str, what: str) -> str | None:
    if not table.is_facilitator(actor_seat):
        return f"Only the facilitator can {what}."
    return None


@dataclass(frozen=True)
class StartClass:
    """Start an activity at several tables. The facilitator does, and does not sit."""

    kind: str
    title: str
    min_players: int
    max_players: int
    tables: int
    options: tuple[tuple[str, str], ...] = ()
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (
            reason := _facilitator_only(table, actor_seat, "start a class")
        ) is not None:
            return reason
        if not 1 <= self.tables <= MAX_TABLES:
            return f"A class has from 1 to {MAX_TABLES} tables."
        if self.min_players < 1 or self.max_players < self.min_players:
            return "That activity has no sensible number of players."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        table.class_serial += 1
        class_id = f"class-{table.class_serial}"
        made: list[str] = []
        for _ in range(self.tables):
            table.activity_serial += 1
            activity = Activity(
                id=f"activity-{table.activity_serial}",
                kind=self.kind,
                title=self.title,
                min_players=self.min_players,
                max_players=self.max_players,
                seats=(),
                options=dict(self.options),
                class_id=class_id,
            )
            table.activities[activity.id] = activity
            made.append(activity.id)
        group = ClassGroup(
            id=class_id,
            kind=self.kind,
            title=self.title,
            tables=tuple(made),
            options=dict(self.options),
        )
        table.classes[class_id] = group
        return [_class_patch(group)]


@dataclass(frozen=True)
class AssignClassTables:
    """Seat people at a class's tables, one list per table. Before any table begins."""

    class_id: str
    assignments: tuple[tuple[str, ...], ...]
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.class_id)) is not None:
            return reason
        if (r := _facilitator_only(table, actor_seat, "seat people")) is not None:
            return r
        group = table.classes[self.class_id]
        if len(self.assignments) != len(group.tables):
            return "Give each table its people."
        if any(table.activities[t].status != "signup" for t in group.tables):
            return "A table has already begun, so people cannot be moved."
        everyone = [seat for people in self.assignments for seat in people]
        if len(set(everyone)) != len(everyone):
            return "Each person can sit at only one table."
        for seat in everyone:
            known = table.seats.get(seat)
            if known is None or known.participant_id is None:
                return "Choose people who are at the table."
            if known.is_facilitator:
                return "The facilitator runs the class and does not sit at a table."
        for tid, people in zip(group.tables, self.assignments, strict=True):
            if len(people) > table.activities[tid].max_players:
                return (
                    f"{table.activities[tid].title} takes at most "
                    f"{table.activities[tid].max_players} people a table."
                )
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        group = table.classes[self.class_id]
        for tid, people in zip(group.tables, self.assignments, strict=True):
            table.activities[tid].seats = people
        return [_class_patch(group)]


@dataclass(frozen=True)
class ChangeActivitySeats:
    """The facilitator changes who sits at a table of a class, begun or not.

    ``added_zones`` are the zones the game layer has already made for people
    who are new to a running table. A person who leaves takes their own
    zones, and what is in them, off the table.
    """

    activity_id: str
    seats: tuple[str, ...]
    added_zones: tuple[str, ...] = ()
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        activity = table.activities.get(self.activity_id)
        if activity is None:
            return "That table is not running any more."
        if not activity.class_id:
            return "Only the tables of a class are moved between."
        if (r := _facilitator_only(table, actor_seat, "move people")) is not None:
            return r
        if len(set(self.seats)) != len(self.seats):
            return "Each person can sit at a table only once."
        if len(self.seats) > activity.max_players:
            return f"{activity.title} takes at most {activity.max_players} a table."
        for seat in self.seats:
            known = table.seats.get(seat)
            if known is None or known.participant_id is None:
                return "Choose people who are at the table."
            if known.is_facilitator:
                return "The facilitator runs the class and does not sit at a table."
            for other_id in table.classes[activity.class_id].tables:
                other = table.activities.get(other_id)
                if (
                    other is not None
                    and other.id != activity.id
                    and seat in other.seats
                ):
                    return "Take them off their table first."
        if any(zone not in table.zones for zone in self.added_zones):
            return "A new person's zones were not made."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        activity = table.activities[self.activity_id]
        gone = set(activity.seats) - set(self.seats)
        patches: list[Patch] = []
        kept: list[str] = []
        for zone_id in activity.zones:
            zone = table.zones.get(zone_id)
            if zone is not None and zone.owner_seat in gone:
                for piece in table.pieces_in_zone(zone_id):
                    del table.pieces[piece.id]
                    patches.append(
                        Patch(kind="piece", op="remove", entity_id=piece.id, fields={})
                    )
                del table.zones[zone_id]
                patches.append(
                    Patch(kind="zone", op="remove", entity_id=zone_id, fields={})
                )
            else:
                kept.append(zone_id)
        activity.zones = (*kept, *self.added_zones)
        activity.seats = self.seats
        patches.append(_class_patch(table.classes[activity.class_id]))
        return patches


@dataclass(frozen=True)
class StartClassTimer:
    """Start (or restart) one countdown, for every table. Advisory: nothing reads it."""

    class_id: str
    seconds: int
    now: float
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.class_id)) is not None:
            return reason
        if (r := _facilitator_only(table, actor_seat, "set the timer")) is not None:
            return r
        if not 1 <= self.seconds <= MAX_TIMER_SECONDS:
            return "Choose a time between a second and three hours."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        group = table.classes[self.class_id]
        group.timer_seconds = self.seconds
        group.timer_ends_at = self.now + self.seconds
        return [_class_patch(group)]


@dataclass(frozen=True)
class ClearClassTimer:
    """Take the countdown away."""

    class_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.class_id)) is not None:
            return reason
        return _facilitator_only(table, actor_seat, "clear the timer")

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        group = table.classes[self.class_id]
        group.timer_seconds = 0
        group.timer_ends_at = None
        return [_class_patch(group)]


@dataclass(frozen=True)
class PushClassPrompt:
    """Show a prompt on every screen of every table. An empty text takes it away."""

    class_id: str
    text: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.class_id)) is not None:
            return reason
        return _facilitator_only(table, actor_seat, "push a prompt")

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        group = table.classes[self.class_id]
        group.prompt = self.text
        group.prompt_serial += 1
        return [_class_patch(group)]


# The partner of a table paired with no real table: a hypothetical one,
# whose decision only the facilitator may set.
HYPOTHETICAL_TABLE = "hypothetical"


@dataclass(frozen=True)
class PairTables:
    """Pair two tables of a class, so their decisions are read together.

    ``second`` may be ``HYPOTHETICAL_TABLE``: the table is paired with a
    partner that is not in the room, whose decision the facilitator sets
    (or leaves unset).
    """

    class_id: str
    first: str
    second: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.class_id)) is not None:
            return reason
        if (r := _facilitator_only(table, actor_seat, "pair tables")) is not None:
            return r
        group = table.classes[self.class_id]
        if self.first == self.second:
            return "Pair two different tables."
        if self.first not in group.tables or (
            self.second not in group.tables and self.second != HYPOTHETICAL_TABLE
        ):
            return "Both tables must belong to this class."
        if any(t in pair for pair in group.pairs for t in (self.first, self.second)):
            return "A table can have only one partner. Unpair it first."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        group = table.classes[self.class_id]
        group.pairs = (*group.pairs, (self.first, self.second))
        return [_class_patch(group)]


@dataclass(frozen=True)
class UnpairTables:
    """Take a table out of its pair, and forget both tables' decisions."""

    class_id: str
    table_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.class_id)) is not None:
            return reason
        if (r := _facilitator_only(table, actor_seat, "unpair tables")) is not None:
            return r
        group = table.classes[self.class_id]
        if not any(self.table_id in pair for pair in group.pairs):
            return "That table is not paired."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        group = table.classes[self.class_id]
        for pair in group.pairs:
            if self.table_id in pair:
                for member in pair:
                    group.decisions.pop(member, None)
                    group.proposed.pop(member, None)
        group.pairs = tuple(p for p in group.pairs if self.table_id not in p)
        return [_class_patch(group)]


@dataclass(frozen=True)
class SetClassDecision:
    """Record what a table decided, in the activity's own words. Empty clears it.

    Someone at the table proposes it; it counts once the facilitator confirms
    it. The facilitator may also set any table's decision directly, which
    confirms it and clears what was proposed.

    Whether the words are ones the activity knows is for the layer above to
    check; the model only keeps them.
    """

    class_id: str
    table_id: str
    decision: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.class_id)) is not None:
            return reason
        group = table.classes[self.class_id]
        if self.table_id == HYPOTHETICAL_TABLE:
            if (
                r := _facilitator_only(
                    table, actor_seat, "decide for a hypothetical table"
                )
            ) is not None:
                return r
            if not any(self.table_id in pair for pair in group.pairs):
                return "Pair a table with a hypothetical one first."
            return None
        if self.table_id not in group.tables:
            return "That table is not part of this class."
        sits_there = actor_seat in table.activities[self.table_id].seats
        if not table.is_facilitator(actor_seat) and not sits_there:
            return "Only the facilitator or someone at that table can record it."
        if not any(self.table_id in pair for pair in group.pairs):
            return "Pair that table first."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        group = table.classes[self.class_id]
        if not table.is_facilitator(actor_seat):
            if self.decision:
                group.proposed[self.table_id] = self.decision
            else:
                group.proposed.pop(self.table_id, None)
            return [_class_patch(group)]
        group.proposed.pop(self.table_id, None)
        if self.decision:
            group.decisions[self.table_id] = self.decision
        else:
            group.decisions.pop(self.table_id, None)
        return [_class_patch(group)]


@dataclass(frozen=True)
class EndClass:
    """End the class: every table's zones and pieces leave the room."""

    class_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_missing(table, self.class_id)) is not None:
            return reason
        return _facilitator_only(table, actor_seat, "end a class")

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        group = table.classes[self.class_id]
        patches: list[Patch] = []
        for activity_id in group.tables:
            if activity_id in table.activities:
                patches += EndActivity(activity_id).apply(table, actor_seat)
        del table.classes[self.class_id]
        patches.append(
            Patch(
                kind="table", op="event", entity_id=group.id, fields={"type": "class"}
            )
        )
        return patches
