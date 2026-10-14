"""Turning a game definition into operations on a table.

Everything an exercise does to its table - building it, seating someone,
pressing a macro button - is built here as one ``Transaction``: the exact
operations to apply, in order, which ``run_op`` then applies all together or
not at all. Building runs each operation against a private copy of the
table as it goes, so a step is compiled against what the steps before it
did, and a step that cannot happen refuses the whole thing with the model's
own reason.

The transaction that comes out is concrete: every piece id it spawns, every
piece it moves, named. That is what the event log records, so a table can be
replayed from its log without the definition that built it.

Nothing here knows any particular exercise. It reads the definition.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Sequence

from sandbox.games.definition import (
    ClearInkStep,
    CollectStep,
    DealStep,
    DrawStep,
    FlipStep,
    ResetTableStep,
    ResetZoneStep,
    SetupStep,
    ShuffleStep,
    SpawnDeckStep,
    SpawnStep,
    Step,
    ZoneSpec,
)
from sandbox.games.hatch import GameContext, GameFunction, MacroRefused, Moment
from sandbox.games.loader import Game
from sandbox.model import (
    AddSeat,
    AddZone,
    ClearInk,
    Deal,
    Draw,
    Flip,
    MoveToZone,
    Operation,
    Rect,
    Reject,
    ResetTable,
    ResetZone,
    SetProp,
    Shuffle,
    Spawn,
    Table,
    Transaction,
    Visibility,
    new_op_id,
)
from sandbox.model.types import PieceKind

SEAT_TINTS = 6


class SetupFailedError(Exception):
    """A table or seat could not be built. A definition bug, never a person's."""


class _Refused(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _seat_number(seat_id: str) -> tuple[int, str]:
    match = re.fullmatch(r".*?(\d+)", seat_id)
    return (int(match.group(1)) if match else 0, seat_id)


def seat_order(table: Table) -> tuple[str, ...]:
    """Every seat at the table, in the order people sat down."""
    return tuple(sorted(table.seats, key=_seat_number))


def seat_zone_id(zone_id: str, seat_id: str) -> str:
    """The id of ``seat_id``'s copy of the per-seat zone ``zone_id``."""
    return f"{zone_id}-{seat_id}"


def _add_zone(
    spec: ZoneSpec, *, seat_id: str | None, seat_index: int, label: str
) -> AddZone:
    x, y, width, height = spec.rect
    dx, dy = spec.step
    return AddZone(
        zone_id=spec.id if seat_id is None else seat_zone_id(spec.id, seat_id),
        kind=spec.kind,
        label=label,
        geometry=Rect(
            x=x + dx * seat_index, y=y + dy * seat_index, width=width, height=height
        ),
        visibility=spec.visibility,
        layout=spec.layout,
        owner_seat=seat_id,
        capacity=spec.capacity,
    )


class _Builder:
    """Collects the operations of one transaction, trying each as it goes."""

    def __init__(self, game: Game | None, table: Table, actor_seat: str) -> None:
        self.game = game
        self.trial = copy.deepcopy(table)
        self.actor_seat = actor_seat
        self.steps: list[Operation] = []

    # -- running ----------------------------------------------------------

    def run(self, operation: Operation) -> None:
        reason = operation.validate(self.trial, self.actor_seat)
        if reason is not None:
            raise _Refused(reason)
        operation.apply(self.trial, self.actor_seat)
        self.steps.append(operation)

    def transaction(self, name: str, label: str) -> Transaction:
        return Transaction(steps=tuple(self.steps), name=name, label=label)

    # -- what the definition names ----------------------------------------

    def _game(self) -> Game:
        assert self.game is not None
        return self.game

    def context(
        self, *, macro_id: str | None = None, seat_id: str | None = None
    ) -> GameContext:
        return GameContext(
            actor_seat=self.actor_seat,
            seats=seat_order(self.trial),
            per_seat_zones=self._game().per_seat_zones,
            macro_id=macro_id,
            seat_id=seat_id,
        )

    def zones(self, zone_id: str) -> list[str]:
        """The zones on the table a definition zone id means, in seat order."""
        if zone_id not in self._game().per_seat_zones:
            return [zone_id]
        found = (seat_zone_id(zone_id, seat) for seat in seat_order(self.trial))
        return [zone for zone in found if zone in self.trial.zones]

    def call(self, function: GameFunction, context: GameContext) -> None:
        try:
            operations = function(copy.deepcopy(self.trial), context)
        except MacroRefused as refusal:
            raise _Refused(refusal.reason) from refusal
        for operation in operations:
            self.run(operation)

    def hooks(self, moment: Moment, context: GameContext) -> None:
        for function in self._game().hooks.get(moment, ()):
            self.call(function, context)

    # -- seats and zones ----------------------------------------------------

    def shared_zones(self) -> None:
        for spec in self._game().definition.zones:
            if not spec.per_seat:
                self.run(_add_zone(spec, seat_id=None, seat_index=0, label=spec.label))

    def seat(self, *, participant_id: str | None, is_facilitator: bool) -> str:
        index = len(self.trial.seats)
        seat_id = f"seat-{index + 1}"
        labels = () if self.game is None else self.game.definition.seats.labels
        label = labels[index] if index < len(labels) else f"Seat {index + 1}"
        self.run(
            AddSeat(
                seat_id=seat_id,
                label=label,
                tint_index=index % SEAT_TINTS,
                is_facilitator=is_facilitator,
                participant_id=participant_id,
            )
        )
        if self.game is not None:
            for spec in self.game.definition.zones:
                if spec.per_seat:
                    self.run(
                        _add_zone(
                            spec,
                            seat_id=seat_id,
                            seat_index=index,
                            label=f"{spec.label} · {label}",
                        )
                    )
            self.hooks("seat_change", self.context(seat_id=seat_id))
        return seat_id

    # -- steps --------------------------------------------------------------

    def step(self, step: Step) -> None:
        game = self._game()
        if isinstance(step, SetupStep):
            for inner in game.definition.setup:
                self.step(inner)
            self.hooks("after_setup", self.context())
        elif isinstance(step, SpawnDeckStep):
            self._spawn_deck(step)
        elif isinstance(step, SpawnStep):
            self._spawn(step)
        elif isinstance(step, ShuffleStep):
            for zone in self.zones(step.zone):
                self.run(Shuffle(zone_id=zone))
        elif isinstance(step, DealStep):
            self._deal(step)
        elif isinstance(step, DrawStep):
            for zone in self.zones(step.to):
                self._draw(step.from_zone, zone, step.count, step.face_up)
        elif isinstance(step, CollectStep):
            self._collect(step)
        elif isinstance(step, FlipStep):
            for zone in self.zones(step.zone):
                for piece in self.trial.pieces_in_zone(zone):
                    if piece.face_up is not step.face_up:
                        self.run(Flip(piece_id=piece.id, face_up=step.face_up))
        elif isinstance(step, ResetTableStep):
            self.run(ResetTable())
        elif isinstance(step, ResetZoneStep):
            for zone in self.zones(step.zone):
                self.run(ResetZone(zone_id=zone))
        elif isinstance(step, ClearInkStep):
            self.run(ClearInk(everyone=True))

    def _spawn_deck(self, step: SpawnDeckStep) -> None:
        deck = next(
            d for d in self._game().definition.components.decks if d.id == step.deck
        )
        for zone in self.zones(step.zone):
            for card in self._game().decks[step.deck]:
                # A fresh random id for each card: an id derived from the
                # card would name it to everyone, face down or not.
                self.run(
                    Spawn(
                        component_id=card.component_id,
                        kind=deck.kind,
                        zone_id=zone,
                        piece_ids=(new_op_id(),),
                    )
                )
            # The cards went in in file order, and everyone saw their ids
            # arrive in that order. A shuffle is what makes those ids stop
            # meaning anything; a hidden zone always gets one.
            if self.trial.zones[zone].visibility is Visibility.HIDDEN:
                self.run(Shuffle(zone_id=zone))

    def _spawn(self, step: SpawnStep) -> None:
        spec = next(
            p
            for p in self._game().definition.components.pieces
            if p.id == step.component
        )
        for zone in self.zones(step.zone):
            piece_ids = tuple(new_op_id() for _ in range(step.count))
            self.run(
                Spawn(
                    component_id=spec.id,
                    kind=spec.kind,
                    zone_id=zone,
                    count=step.count,
                    piece_ids=piece_ids,
                )
            )
            if spec.kind is PieceKind.DIE and spec.faces:
                for piece_id in piece_ids:
                    self.run(
                        SetProp(piece_id=piece_id, key="faces", value=list(spec.faces))
                    )

    def _turn(self, piece_ids: Sequence[str], face_up: bool | None) -> None:
        if face_up is None:
            return
        for piece_id in piece_ids:
            if self.trial.pieces[piece_id].face_up is not face_up:
                self.run(Flip(piece_id=piece_id, face_up=face_up))

    def _deal(self, step: DealStep) -> None:
        destinations = tuple(self.zones(step.to))
        if not destinations:
            raise _Refused("There is nobody at the table to deal to.")
        needed = step.count * len(destinations)
        # Deal takes from the top of the pile, so these are the pieces it
        # will move. Which card each one is does not matter here.
        dealt = [
            piece.id for piece in self.trial.pieces_in_zone(step.from_zone)[-needed:]
        ]
        self.run(
            Deal(from_zone=step.from_zone, to_zones=destinations, count_each=step.count)
        )
        self._turn(dealt, step.face_up)

    def _draw(
        self, source: str, destination: str, count: int, face_up: bool | None
    ) -> None:
        drawn = [piece.id for piece in self.trial.pieces_in_zone(source)[-count:]]
        self.run(Draw(count=count, from_zone=source, to_zone=destination))
        self._turn(drawn, face_up)

    def _collect(self, step: CollectStep) -> None:
        if step.from_zones:
            sources = [
                zone for source in step.from_zones for zone in self.zones(source)
            ]
        else:
            sources = [zone for zone in self.trial.zones if zone != step.to]
        moved: list[str] = []
        for zone in sources:
            for piece in self.trial.pieces_in_zone(zone):
                if step.kinds and piece.kind not in step.kinds:
                    continue
                self.run(MoveToZone(piece_id=piece.id, zone_id=step.to))
                moved.append(piece.id)
        self._turn(moved, step.face_up)


# -- what the room service and the live room ask for -------------------------


def build_table(
    game: Game | None, table: Table, *, participant_id: str | None
) -> tuple[str, Transaction]:
    """Everything a new room's table needs, with its facilitator seated.

    Shared zones first, so their place in the zone list - which is the order
    the table draws them in - does not depend on how many people join; then
    the facilitator's seat and its own zones; then the definition's setup.
    Returns the facilitator's seat id and the transaction to apply as them.
    """
    builder = _Builder(game, table, actor_seat="seat-1")
    try:
        if game is not None:
            builder.shared_zones()
        seat_id = builder.seat(participant_id=participant_id, is_facilitator=True)
        if game is not None:
            builder.step(SetupStep(op="setup"))
    except _Refused as refusal:
        raise SetupFailedError(refusal.reason) from refusal
    return seat_id, builder.transaction(name="setup", label="Set up the table")


def build_seat(
    game: Game | None, table: Table, *, participant_id: str | None
) -> tuple[str, Transaction]:
    """A new seat for someone joining, with its own zones. Returns its id."""
    seat_id = f"seat-{len(table.seats) + 1}"
    builder = _Builder(game, table, actor_seat=seat_id)
    try:
        builder.seat(participant_id=participant_id, is_facilitator=False)
    except _Refused as refusal:
        raise SetupFailedError(refusal.reason) from refusal
    return seat_id, builder.transaction(name=f"seat:{seat_id}", label="Take a seat")


def build_macro(
    game: Game, table: Table, actor_seat: str, macro_id: str
) -> Transaction | Reject:
    """What pressing ``macro_id`` does now, or why it cannot be pressed."""
    spec = game.definition.macro(macro_id)
    if spec is None:
        return Reject(f"This exercise has no button called {macro_id!r}.")
    if spec.who == "facilitator" and not table.is_facilitator(actor_seat):
        return Reject(f"Only the facilitator can use “{spec.label}”.")
    builder = _Builder(game, table, actor_seat)
    try:
        builder.hooks("before_macro", builder.context(macro_id=macro_id))
        if spec.steps is not None:
            for step in spec.steps:
                builder.step(step)
        else:
            assert spec.python is not None
            builder.call(
                game.macro_functions[spec.python], builder.context(macro_id=macro_id)
            )
    except _Refused as refusal:
        return Reject(refusal.reason)
    return builder.transaction(name=f"macro:{macro_id}", label=spec.label)


def announcement(game: Game, macro_id: str, name: str) -> str:
    """What the table is told after ``name`` pressed ``macro_id``."""
    spec = game.definition.macro(macro_id)
    if spec is None:
        return ""
    return spec.announce.format(name=name, label=spec.label)


__all__ = [
    "SetupFailedError",
    "announcement",
    "build_macro",
    "build_seat",
    "build_table",
    "seat_order",
    "seat_zone_id",
]
