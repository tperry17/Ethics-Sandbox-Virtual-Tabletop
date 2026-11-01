"""What a debrief is made of, and the registry of exercises that have one.

A debrief is built only from what Prompts 10-12 already log: the event log,
and the table rebuilt from it. It never ranks or scores people and never says
which choice was right. Each exercise's own reading of the log lives in its
game package (``value_cards_trading/debrief.py``, ``democracy_simulation/
debrief.py``) and registers here by the game's slug; the web layer only asks
this module for the sections and draws them.

The shapes are plain: a section holds blocks of text, a table, bars, or a
list. A bar chart is one shared scale with direct labels.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sandbox.games.loader import Game
from sandbox.model import Activity, ClassGroup, Table


@dataclass(frozen=True)
class LogEvent:
    """One row of a room's log, in the form the debrief and replay read."""

    seq: int
    created_at: datetime
    actor_seat: str | None
    op_type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class Entry:
    """One leaf operation of the log, with what it was done inside.

    ``macro`` is the name of the enclosing transaction (``macro:deal``) or
    ``""`` for an operation logged on its own. ``activity_id`` is the
    activity a button was pressed in, when the log says.
    """

    seq: int
    at: datetime
    actor_seat: str | None
    op_type: str
    payload: dict[str, Any]
    macro: str = ""
    activity_id: str = ""


def leaf_entries(events: Sequence[LogEvent]) -> list[Entry]:
    """Every operation in the log, a transaction's steps in place of itself."""
    entries: list[Entry] = []
    for event in events:
        if event.op_type == "Transaction":
            for step in event.payload["steps"]:
                entries.append(
                    Entry(
                        seq=event.seq,
                        at=event.created_at,
                        actor_seat=event.actor_seat,
                        op_type=step["op_type"],
                        payload=step["payload"],
                        macro=str(event.payload.get("name", "")),
                        activity_id=str(event.payload.get("activity_id", "")),
                    )
                )
        else:
            entries.append(
                Entry(
                    seq=event.seq,
                    at=event.created_at,
                    actor_seat=event.actor_seat,
                    op_type=event.op_type,
                    payload=event.payload,
                )
            )
    return entries


# -- what a debrief page holds ----------------------------------------------------


@dataclass(frozen=True)
class Block:
    """One piece of a section: ``text``, a ``table``, ``bars`` or a ``list``."""

    kind: str
    title: str = ""
    text: str = ""
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    bars: tuple[tuple[str, int], ...] = ()
    items: tuple[str, ...] = ()


@dataclass(frozen=True)
class Section:
    title: str
    blocks: tuple[Block, ...]
    note: str = ""


def text(body: str, title: str = "") -> Block:
    return Block(kind="text", title=title, text=body)


def table(
    columns: Sequence[str], rows: Sequence[Sequence[str]], title: str = ""
) -> Block:
    return Block(
        kind="table",
        title=title,
        columns=tuple(columns),
        rows=tuple(tuple(row) for row in rows),
    )


def bars(counts: Sequence[tuple[str, int]], title: str = "") -> Block:
    return Block(kind="bars", title=title, bars=tuple(counts))


def checklist(rows: Sequence[tuple[str, str, bool]], title: str = "") -> Block:
    """Things the facilitator may tick: each row is (id, label, ticked)."""
    return Block(
        kind="checklist",
        title=title,
        rows=tuple((i, label, "1" if on else "0") for i, label, on in rows),
    )


def listing(items: Sequence[str], title: str = "") -> Block:
    return Block(kind="list", title=title, items=tuple(items))


def counted(items: Sequence[str]) -> list[tuple[str, int]]:
    """``items`` with how often each occurs, most often first, ties in name order.

    Only ever used for things (cards, choices), never for people.
    """
    counts = Counter(items)
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))


# -- what an exercise's reader is given ---------------------------------------------


@dataclass(frozen=True)
class Context:
    """Everything an exercise's debrief may read, and who is reading it."""

    game: Game
    activity: Activity
    entries: Sequence[Entry]
    final: Table
    table_at: Callable[[int], Table]
    names: Mapping[str, str]
    viewer_seat: str | None
    is_facilitator: bool
    settings: Mapping[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None

    def name(self, seat_id: str) -> str:
        """The person's display name, or the seat's own label."""
        if seat_id in self.names:
            return self.names[seat_id]
        seat = self.final.seats.get(seat_id)
        return seat.label if seat is not None else seat_id

    def label(self, seat_id: str) -> str:
        seat = self.final.seats.get(seat_id)
        return seat.label if seat is not None else seat_id

    def mine(self, seat_id: str) -> bool:
        return self.viewer_seat is not None and self.viewer_seat == seat_id


@dataclass(frozen=True)
class ClassContext:
    """A class's tables, each already read, for the class page."""

    game: Game
    group: ClassGroup
    tables: Sequence[Context]
    final: Table


ActivityBuilder = Callable[[Context], list[Section]]
ClassBuilder = Callable[[ClassContext], list[Section]]

ACTIVITY_DEBRIEFS: dict[str, ActivityBuilder] = {}
CLASS_DEBRIEFS: dict[str, ClassBuilder] = {}


def activity_debrief(kind: str) -> Callable[[ActivityBuilder], ActivityBuilder]:
    def register(function: ActivityBuilder) -> ActivityBuilder:
        ACTIVITY_DEBRIEFS[kind] = function
        return function

    return register


def class_debrief(kind: str) -> Callable[[ClassBuilder], ClassBuilder]:
    def register(function: ClassBuilder) -> ClassBuilder:
        CLASS_DEBRIEFS[kind] = function
        return function

    return register


# -- helpers shared by every exercise ------------------------------------------------


def activity_entries(entries: Sequence[Entry], activity: Activity) -> list[Entry]:
    """The entries that belong to ``activity``.

    A button press carries its activity's id. An operation logged on its own
    (a swap, a card shown, a proposal written on) belongs to it when its actor
    sits in it.
    """
    seats = set(activity.seats)
    return [
        entry
        for entry in entries
        if entry.activity_id == activity.id
        or (not entry.activity_id and entry.actor_seat in seats)
    ]


def piece_ids_of(entries: Sequence[Entry]) -> dict[str, str]:
    """Each spawned piece's id and the component it is, from the Spawn steps."""
    found: dict[str, str] = {}
    for entry in entries:
        if entry.op_type != "Spawn":
            continue
        for piece_id in entry.payload.get("piece_ids") or ():
            found[piece_id] = str(entry.payload["component_id"])
    return found


def minutes(seconds: float) -> str:
    """``seconds`` as plain words: ``45 s``, ``3 min``, ``12 min 30 s``."""
    whole = int(round(seconds))
    if whole < 60:
        return f"{whole} s"
    mins, secs = divmod(whole, 60)
    return f"{mins} min" if secs == 0 else f"{mins} min {secs} s"


def clock(moment: datetime, started: datetime | None) -> str:
    """When ``moment`` was, as time since the activity began."""
    if started is None:
        return moment.strftime("%H:%M:%S")
    return minutes(max(0.0, (moment - started).total_seconds()))


IDLE_AFTER_SECONDS = 180.0


def idle_stretches(
    entries: Sequence[Entry], threshold: float = IDLE_AFTER_SECONDS
) -> list[tuple[datetime, float]]:
    """Stretches of at least ``threshold`` seconds with nothing logged.

    Silence in the log is not silence at the table (people talk on the
    call), so this is only a place to ask what was happening.
    """
    stamps = sorted({entry.at for entry in entries})
    gaps: list[tuple[datetime, float]] = []
    for before, after in zip(stamps, stamps[1:], strict=False):
        seconds = (after - before).total_seconds()
        if seconds >= threshold:
            gaps.append((before, seconds))
    return gaps


def timing_block(
    spans: Sequence[tuple[str, float | None]],
    entries: Sequence[Entry],
    started: datetime | None,
) -> Block:
    """How long each part took, and where the log went quiet."""
    rows: list[tuple[str, ...]] = [
        (label, minutes(seconds) if seconds is not None else "not reached")
        for label, seconds in spans
    ]
    for before, seconds in idle_stretches(entries):
        rows.append(
            (f"Nothing logged, from {clock(before, started)}", minutes(seconds))
        )
    return table(["Part", "How long"], rows)


def outcomes_and_questions(game: Game, outcomes: Sequence[Any]) -> Section:
    """The exercise's debrief questions, grouped under its learning outcomes."""
    blocks: list[Block] = []
    titles = [outcome.title for outcome in outcomes]
    grouped: dict[str, list[str]] = {title: [] for title in titles}
    loose: list[str] = []
    for prompt in game.prompts:
        key = prompt.group or ""
        if key in grouped:
            grouped[key].append(prompt.text)
        else:
            loose.append(prompt.text)
    for outcome in outcomes:
        blocks.append(listing(grouped[outcome.title], title=outcome.title))
    if loose:
        blocks.append(listing(loose, title="Other questions"))
    return Section(title="Questions for discussion", blocks=tuple(blocks))


__all__ = [
    "ACTIVITY_DEBRIEFS",
    "ActivityBuilder",
    "Block",
    "CLASS_DEBRIEFS",
    "ClassBuilder",
    "ClassContext",
    "Context",
    "Entry",
    "LogEvent",
    "Section",
    "activity_debrief",
    "activity_entries",
    "bars",
    "checklist",
    "class_debrief",
    "clock",
    "counted",
    "idle_stretches",
    "leaf_entries",
    "listing",
    "minutes",
    "outcomes_and_questions",
    "piece_ids_of",
    "table",
    "text",
    "timing_block",
]
