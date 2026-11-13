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
import dataclasses
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sandbox.games.definition import (
    ClearInkStep,
    CollectStep,
    DealStep,
    DrawStep,
    FlipStep,
    ResetTableStep,
    ResetZoneStep,
    RoomDeck,
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
    SYSTEM_SEAT,
    AddSeat,
    AddZone,
    BeginActivity,
    ChangeActivitySeats,
    ClearInk,
    Deal,
    Draw,
    Flip,
    Lock,
    Move,
    MoveToZone,
    Operation,
    Rect,
    Reject,
    RemoveZone,
    ResetTable,
    ResetZone,
    SetProp,
    SetText,
    Shuffle,
    Spawn,
    Table,
    Transaction,
    Visibility,
    new_op_id,
)
from sandbox.model.types import PieceKind

SEAT_TINTS = 6

# A pile added from a room's Pieces menu is a zone of its own, named with
# this prefix so the room's reset can take it away again.
ADDED_DECK_PREFIX = "added-deck-"
# How many such piles a table may hold at once.
MAX_ADDED_DECKS = 12


def _matches(fields: Mapping[str, str] | None, wanted: Mapping[str, str]) -> bool:
    """Whether a deck row has every wanted column value, ignoring case."""
    if fields is None:
        return not wanted
    return all(fields.get(c, "").casefold() == v.casefold() for c, v in wanted.items())


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


@dataclass(frozen=True)
class Scope:
    """Where an activity lives in a room: its zones' names, players and place.

    Every zone an activity makes is named ``<activity id>:<definition id>``,
    its per-seat zones belong to the activity's players only, and its
    rectangles are moved by ``origin`` so they sit clear of the sandbox.
    """

    activity_id: str
    seats: tuple[str, ...]
    origin: tuple[float, float]
    options: Mapping[str, str] = field(default_factory=dict)

    @property
    def prefix(self) -> str:
        return f"{self.activity_id}:"


ACTIVITY_SPACING = 2600.0


def scope_of(table: Table, activity_id: str) -> Scope:
    """The scope of an activity in ``table``, placed by its serial number."""
    activity = table.activities[activity_id]
    serial = _seat_number(activity_id)[0]
    return Scope(
        activity_id=activity_id,
        seats=activity.seats,
        origin=(ACTIVITY_SPACING * serial, 0.0),
        options=dict(activity.options),
    )


def _add_zone(
    spec: ZoneSpec,
    *,
    seat_id: str | None,
    seat_index: int,
    label: str,
    scope: Scope | None = None,
) -> AddZone:
    x, y, width, height = spec.rect
    dx, dy = spec.step
    prefix = "" if scope is None else scope.prefix
    ox, oy = (0.0, 0.0) if scope is None else scope.origin
    zone_id = prefix + spec.id
    return AddZone(
        zone_id=zone_id if seat_id is None else seat_zone_id(zone_id, seat_id),
        kind=spec.kind,
        label=label,
        geometry=Rect(
            x=ox + x + dx * seat_index,
            y=oy + y + dy * seat_index,
            width=width,
            height=height,
        ),
        visibility=spec.visibility,
        layout=spec.layout,
        owner_seat=seat_id,
        capacity=spec.capacity,
        owner_moves_only=spec.owner_moves_only,
    )


class _Builder:
    """Collects the operations of one transaction, trying each as it goes."""

    def __init__(
        self,
        game: Game | None,
        table: Table,
        actor_seat: str,
        scope: Scope | None = None,
        options: Mapping[str, str] | None = None,
    ) -> None:
        self.game = game
        self.scope = scope
        # What was chosen when the activity was opened; a room game's table,
        # which has no activity, takes each option's first choice.
        self.options: Mapping[str, str] = (
            scope.options
            if scope is not None
            else options
            if options is not None
            else ({} if game is None else game.definition.default_options())
        )
        self.trial = copy.deepcopy(table)
        # Who each step is tried as. An activity's buttons act for the room.
        self.actor_seat = SYSTEM_SEAT if scope is not None else actor_seat
        self.operator = actor_seat
        self.steps: list[Operation] = []

    # -- running ----------------------------------------------------------

    def run(self, operation: Operation) -> None:
        reason = operation.validate(self.trial, self.actor_seat)
        if reason is not None:
            raise _Refused(reason)
        operation.apply(self.trial, self.actor_seat)
        self.steps.append(operation)

    def transaction(self, name: str, label: str) -> Transaction:
        return Transaction(
            steps=tuple(self.steps),
            name=name,
            label=label,
            system=self.scope is not None,
        )

    # -- what the definition names ----------------------------------------

    def _game(self) -> Game:
        assert self.game is not None
        return self.game

    def context(
        self, *, macro_id: str | None = None, seat_id: str | None = None
    ) -> GameContext:
        return GameContext(
            actor_seat=self.operator,
            seats=self._seats(),
            prefix="" if self.scope is None else self.scope.prefix,
            per_seat_zones=self._game().per_seat_zones,
            macro_id=macro_id,
            seat_id=seat_id,
            options=self.options,
            cards=self._game().cards(),
        )

    def _seats(self) -> tuple[str, ...]:
        """The seats a step means by "every seat": the activity's, if scoped."""
        if self.scope is not None:
            return self.scope.seats
        return seat_order(self.trial)

    def zone(self, zone_id: str) -> str:
        """The id on the table of a shared zone the definition names."""
        return zone_id if self.scope is None else self.scope.prefix + zone_id

    def zones(self, zone_id: str) -> list[str]:
        """The zones on the table a definition zone id means, in seat order."""
        named = self.zone(zone_id)
        if zone_id not in self._game().per_seat_zones:
            return [named]
        found = (seat_zone_id(named, seat) for seat in self._seats())
        return [zone for zone in found if zone in self.trial.zones]

    def scope_zones(self) -> list[str]:
        """Every zone on the table that belongs to this builder's activity."""
        if self.scope is None:
            return list(self.trial.zones)
        return [z for z in self.trial.zones if z.startswith(self.scope.prefix)]

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

    def _wanted(self, spec: ZoneSpec) -> bool:
        """Whether the options chosen include the zone (see ``ZoneSpec.when``)."""
        return all(self.options.get(k) == v for k, v in spec.when.items())

    def shared_zones(self) -> None:
        for spec in self._game().definition.zones:
            if not spec.per_seat and self._wanted(spec):
                self.run(
                    _add_zone(
                        spec,
                        seat_id=None,
                        seat_index=0,
                        label=spec.label,
                        scope=self.scope,
                    )
                )

    def activity_seat_zones(self) -> None:
        """Each of the activity's players gets their own copy of per-seat zones."""
        assert self.scope is not None
        for index, seat_id in enumerate(self.scope.seats):
            label = self.trial.seats[seat_id].label
            for spec in self._game().definition.zones:
                if spec.per_seat and self._wanted(spec):
                    self.run(
                        _add_zone(
                            spec,
                            seat_id=seat_id,
                            seat_index=index,
                            label=f"{spec.label} · {label}",
                            scope=self.scope,
                        )
                    )

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
                if spec.per_seat and self._wanted(spec):
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
            if self.scope is None:
                self.run(ResetTable())
                # Piles added from the Pieces menu go with what was on them.
                for zone_id in list(self.trial.zones):
                    if zone_id.startswith(ADDED_DECK_PREFIX):
                        self.run(RemoveZone(zone_id=zone_id))
            else:
                for zone in self.scope_zones():
                    self.run(ResetZone(zone_id=zone))
        elif isinstance(step, ResetZoneStep):
            for zone in self.zones(step.zone):
                self.run(ResetZone(zone_id=zone))
        elif isinstance(step, ClearInkStep):
            # Ink is the whole room's; an activity clears only its own player's.
            self.run(ClearInk(everyone=self.scope is None))

    def _spawn_deck(self, step: SpawnDeckStep) -> None:
        deck = next(
            d for d in self._game().definition.components.decks if d.id == step.deck
        )
        wanted = {
            column: value.format_map(self.options)
            for column, value in step.where.items()
        }
        cards = [
            card
            for card in self._game().decks[step.deck]
            if _matches(card.fields, wanted)
        ]
        if not cards:
            raise _Refused(f"No cards in {step.deck!r} match {wanted}.")
        for zone in self.zones(step.zone):
            for card in cards:
                # A fresh random id for each card: an id derived from the
                # card would name it to everyone, face down or not.
                self.run(
                    Spawn(
                        component_id=card.component_id,
                        kind=deck.kind,
                        zone_id=zone,
                        piece_ids=(piece_id := new_op_id(),),
                    )
                )
                if not deck.revealable:
                    self.run(SetProp(piece_id=piece_id, key="revealable", value=False))
                if deck.locked:
                    self.run(Lock(piece_id=piece_id))
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
        source = self.zone(step.from_zone)
        # Deal takes from the top of the pile, so these are the pieces it
        # will move. Which card each one is does not matter here.
        dealt = [piece.id for piece in self.trial.pieces_in_zone(source)[-needed:]]
        self.run(Deal(from_zone=source, to_zones=destinations, count_each=step.count))
        self._land(dealt, step.face_up)

    def _draw(
        self, source: str, destination: str, count: int, face_up: bool | None
    ) -> None:
        source = self.zone(source)
        drawn = [piece.id for piece in self.trial.pieces_in_zone(source)[-count:]]
        self.run(Draw(count=count, from_zone=source, to_zone=destination))
        self._land(drawn, face_up)

    def _land(self, piece_ids: Sequence[str], face_up: bool | None) -> None:
        """Turn dealt or drawn pieces as they land.

        With no ``face_up`` in the step, a piece dealt into its owner's
        private hand is turned face up, so the owner can read it and nobody
        else can. Anywhere else it stays as it came off the pile.
        """
        if face_up is not None:
            self._turn(piece_ids, face_up)
            return
        for piece_id in piece_ids:
            zone = self.trial.zones[self.trial.pieces[piece_id].zone_id]
            if zone.visibility is Visibility.PRIVATE_TO_OWNER:
                self._turn([piece_id], True)

    def _collect(self, step: CollectStep) -> None:
        if step.from_zones:
            sources = [
                zone for source in step.from_zones for zone in self.zones(source)
            ]
        else:
            target = self.zone(step.to)
            sources = [zone for zone in self.scope_zones() if zone != target]
        target = self.zone(step.to)
        cards = self._game().cards() if step.where else {}
        moved: list[str] = []
        for zone in sources:
            for piece in self.trial.pieces_in_zone(zone):
                if step.kinds and piece.kind not in step.kinds:
                    continue
                if step.where and not _matches(
                    cards.get(piece.component_id), step.where
                ):
                    continue
                self.run(MoveToZone(piece_id=piece.id, zone_id=target))
                moved.append(piece.id)
        self._turn(moved, step.face_up)


# -- what the room service and the live room ask for -------------------------


def build_table(
    game: Game | None,
    table: Table,
    *,
    participant_id: str | None,
    as_facilitator: bool = False,
    options: Mapping[str, str] | None = None,
) -> tuple[str, Transaction]:
    """Everything a new room's table needs, with its creator seated.

    Nobody is the facilitator unless ``as_facilitator`` says the creator
    chose to be.

    Shared zones first, so their place in the zone list - which is the order
    the table draws them in - does not depend on how many people join; then
    the creator's seat and its own zones; then the definition's setup.
    Returns the creator's seat id and the transaction to apply as them.
    """
    builder = _Builder(game, table, actor_seat="seat-1", options=options)
    try:
        if game is not None:
            builder.shared_zones()
        seat_id = builder.seat(
            participant_id=participant_id, is_facilitator=as_facilitator
        )
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


def may_use_facilitator_button(
    table: Table, seat_id: str, activity_id: str | None
) -> bool:
    """Whether ``seat_id`` may press a button the definition gives the facilitator.

    The facilitator may, always. A button inside an activity may also be
    pressed by its players while nobody in the room holds the role, since no
    activity requires a facilitator.
    """
    if table.is_facilitator(seat_id):
        return True
    if activity_id is None or any(s.is_facilitator for s in table.seats.values()):
        return False
    activity = table.activities.get(activity_id)
    return activity is not None and seat_id in activity.seats


def build_activity_start(
    game: Game, table: Table, actor_seat: str, activity_id: str
) -> Transaction | Reject:
    """Lay out an activity's zones for its players and mark it running."""
    activity = table.activities.get(activity_id)
    if activity is None:
        return Reject("That activity is not running any more.")
    scope = scope_of(table, activity_id)
    builder = _Builder(game, table, actor_seat, scope)
    try:
        before = set(builder.trial.zones)
        builder.shared_zones()
        builder.activity_seat_zones()
        made = tuple(z for z in builder.trial.zones if z not in before)
        builder.step(SetupStep(op="setup"))
        builder.run(BeginActivity(activity_id=activity_id, zones=made))
    except _Refused as refusal:
        return Reject(refusal.reason)
    return dataclasses.replace(
        builder.transaction(
            name=f"activity:{activity_id}", label=f"Begin {activity.title}"
        ),
        activity_id=activity_id,
    )


def _used_seat_indexes(
    builder: _Builder, scope: Scope, seats: tuple[str, ...]
) -> set[int]:
    """Which places along each per-seat zone's step the given seats already hold."""
    used: set[int] = set()
    game = builder._game()
    ox, oy = scope.origin
    for spec in game.definition.zones:
        if not spec.per_seat or not builder._wanted(spec):
            continue
        x, y, _, _ = spec.rect
        dx, dy = spec.step
        for seat in seats:
            zone = builder.trial.zones.get(seat_zone_id(scope.prefix + spec.id, seat))
            if zone is None or not isinstance(zone.geometry, Rect):
                continue
            if dx:
                used.add(round((zone.geometry.x - ox - x) / dx))
            elif dy:
                used.add(round((zone.geometry.y - oy - y) / dy))
            else:
                used.add(0)
    return used


def deck_homes(game: Game) -> dict[str, str]:
    """Where each deck lives: the zone its first ``spawn_deck`` step names."""
    homes: dict[str, str] = {}
    steps = [*game.definition.setup]
    for macro in game.definition.macros:
        steps.extend(macro.steps or ())
    for step in steps:
        if isinstance(step, SpawnDeckStep):
            homes.setdefault(step.deck, step.zone)
    return homes


def _return_cards(builder: _Builder, scope: Scope, gone: set[str]) -> None:
    """Put the cards in the zones of people leaving a table back in their decks.

    Each goes face down into the zone its deck was laid out in, and every
    deck that took a card back is shuffled, so nobody can tell where it went.
    """
    activity = builder.trial.activities[scope.activity_id]
    homes = deck_homes(builder._game())
    shuffled: list[str] = []
    for zone_id in activity.zones:
        zone = builder.trial.zones.get(zone_id)
        if zone is None or zone.owner_seat not in gone:
            continue
        for piece in builder.trial.pieces_in_zone(zone_id):
            deck = piece.component_id.split(":", 1)[0]
            home = homes.get(deck)
            if piece.kind is not PieceKind.CARD or home is None:
                continue
            home_id = scope.prefix + home
            if home_id not in builder.trial.zones:
                continue
            builder.run(Flip(piece_id=piece.id, face_up=False))
            builder.run(MoveToZone(piece_id=piece.id, zone_id=home_id))
            if home_id not in shuffled:
                shuffled.append(home_id)
    for home_id in shuffled:
        if builder.trial.zones[home_id].visibility is Visibility.HIDDEN:
            builder.run(Shuffle(zone_id=home_id))


def _change_seats(builder: _Builder, activity_id: str, seats: tuple[str, ...]) -> None:
    """Add the steps that change who sits at one table, making zones for new people."""
    activity = builder.trial.activities[activity_id]
    scope = scope_of(builder.trial, activity_id)
    builder.scope = scope
    added: list[str] = []
    if activity.status == "running":
        _return_cards(builder, scope, set(activity.seats) - set(seats))
        staying = tuple(seat for seat in seats if seat in activity.seats)
        used = _used_seat_indexes(builder, scope, staying)
        for seat_id in (seat for seat in seats if seat not in activity.seats):
            index = next(i for i in range(len(seats) + len(used) + 1) if i not in used)
            used.add(index)
            label = builder.trial.seats[seat_id].label
            for spec in builder._game().definition.zones:
                if spec.per_seat and builder._wanted(spec):
                    zone = _add_zone(
                        spec,
                        seat_id=seat_id,
                        seat_index=index,
                        label=f"{spec.label} · {label}",
                        scope=scope,
                    )
                    builder.run(zone)
                    added.append(zone.zone_id)
    builder.run(ChangeActivitySeats(activity_id, seats, tuple(added)))


def build_seat_move(
    game: Game,
    table: Table,
    actor_seat: str,
    seat_id: str,
    to_activity_id: str | None,
) -> Transaction | Reject:
    """Take someone off their table in a class and seat them at another (or none).

    One transaction, so nobody is ever at two tables or at none in between.
    A person new to a begun table gets that activity's own zones for them.
    """
    to = table.activities.get(to_activity_id) if to_activity_id else None
    if to_activity_id is not None and (to is None or not to.class_id):
        return Reject("That table is not part of a class.")
    classes = {a.class_id for a in table.activities.values() if seat_id in a.seats}
    classes.discard("")
    if to is not None:
        classes.add(to.class_id)
    if len(classes) != 1:
        return Reject("Choose a table of the class they are in.")
    (class_id,) = classes
    group = table.classes[class_id]
    if group.kind != game.slug:
        return Reject("That class is running something else.")
    builder = _Builder(game, table, actor_seat)
    try:
        for tid in group.tables:
            activity = builder.trial.activities.get(tid)
            if activity is None:
                continue
            if seat_id in activity.seats and tid != to_activity_id:
                _change_seats(
                    builder, tid, tuple(s for s in activity.seats if s != seat_id)
                )
        if to is not None and seat_id not in to.seats:
            _change_seats(builder, to.id, (*to.seats, seat_id))
    except _Refused as refusal:
        return Reject(refusal.reason)
    return builder.transaction(name=f"move:{seat_id}", label="Move a person")


def build_macro(
    game: Game,
    table: Table,
    actor_seat: str,
    macro_id: str,
    activity_id: str | None = None,
) -> Transaction | Reject:
    """What pressing ``macro_id`` does now, or why it cannot be pressed.

    With ``activity_id`` it is an activity's button: its steps name that
    activity's zones and players, not the room's.
    """
    spec = game.definition.macro(macro_id)
    if spec is None:
        return Reject(f"This exercise has no button called {macro_id!r}.")
    if spec.who == "facilitator" and not may_use_facilitator_button(
        table, actor_seat, activity_id
    ):
        label = game.buttons[macro_id].label
        return Reject(f"Only the facilitator can use “{label}”.")
    scope = None
    if activity_id is not None:
        activity = table.activities.get(activity_id)
        if activity is None or activity.status != "running":
            return Reject("That activity is not running.")
        if actor_seat not in activity.seats and not table.is_facilitator(actor_seat):
            return Reject("That button is for the activity's players.")
        scope = scope_of(table, activity_id)
    builder = _Builder(game, table, actor_seat, scope)
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
    return dataclasses.replace(
        builder.transaction(
            name=f"macro:{macro_id}", label=game.buttons[macro_id].label
        ),
        activity_id=activity_id or "",
    )


def announcement(game: Game, macro_id: str, name: str) -> str:
    """What the table is told after ``name`` pressed ``macro_id``."""
    button = game.buttons.get(macro_id)
    if button is None:
        return ""
    return button.announce.format(name=name, label=button.label)


def build_add_piece(
    game: Game, table: Table, component_id: str, x: float, y: float
) -> Transaction | Reject:
    """One piece from the room's Pieces menu, put down at ``x``, ``y``.

    Only a room type has a Pieces menu, and only what it lists can be added.
    The piece goes into the room's ``pieces_zone``, kept inside its edges.
    The new piece's id is random, like every spawned piece's.
    """
    room = game.definition.room
    room_deck = (
        None
        if room is None
        else next((d for d in room.decks if d.id == component_id), None)
    )
    if room_deck is not None:
        return build_add_deck(game, table, room_deck, x, y)
    if room is None or component_id not in room.pieces:
        return Reject("That is not one of this room's pieces.")
    spec = next(p for p in game.definition.components.pieces if p.id == component_id)
    zone = table.zones.get(room.pieces_zone)
    if zone is None or not isinstance(zone.geometry, Rect):
        return Reject("This room has nowhere to put new pieces.")
    rect = zone.geometry
    piece_id = new_op_id()
    return Transaction(
        steps=(
            Spawn(
                component_id=spec.id,
                kind=spec.kind,
                zone_id=zone.id,
                piece_ids=(piece_id,),
            ),
            Move(
                piece_id=piece_id,
                x=min(max(x, rect.x), rect.x + rect.width),
                y=min(max(y, rect.y), rect.y + rect.height),
            ),
        ),
        name=f"add:{spec.id}",
        label=f"Add {(spec.title or spec.kind.value).lower()}",
    )


def build_add_deck(
    game: Game, table: Table, room_deck: RoomDeck, x: float, y: float
) -> Transaction | Reject:
    """A further pile of cards from the room's Pieces menu, centred on ``x``, ``y``.

    The pile is a zone of its own, made like the zone the room deck names
    and kept inside the room's ``pieces_zone``, so it shuffles and deals as
    any deck does. Its cards are spawned as ``spawn_deck`` would, shuffled
    when the pile is hidden. The room's reset takes the zone away again.
    """
    room = game.definition.room
    shape = game.definition.zone_spec(room_deck.shaped_like)
    assert room is not None and shape is not None
    bounds = table.zones.get(room.pieces_zone)
    if bounds is None or not isinstance(bounds.geometry, Rect):
        return Reject("This room has nowhere to put a deck.")
    added = sum(1 for zone_id in table.zones if zone_id.startswith(ADDED_DECK_PREFIX))
    if added >= MAX_ADDED_DECKS:
        return Reject(
            f"The table already has {MAX_ADDED_DECKS} added decks; "
            "reset the table to clear them."
        )
    area = bounds.geometry
    width, height = shape.rect[2], shape.rect[3]
    left = min(max(x - width / 2, area.x), area.x + area.width - width)
    top = min(max(y - height / 2, area.y), area.y + area.height - height)
    zone_id = ADDED_DECK_PREFIX + new_op_id()
    builder = _Builder(game, table, SYSTEM_SEAT)
    try:
        builder.run(
            AddZone(
                zone_id=zone_id,
                kind=shape.kind,
                label=room_deck.title,
                geometry=Rect(x=left, y=top, width=width, height=height),
                visibility=shape.visibility,
                layout=shape.layout,
                capacity=shape.capacity,
                owner_moves_only=shape.owner_moves_only,
            )
        )
        builder.step(
            SpawnDeckStep(
                op="spawn_deck",
                deck=room_deck.deck,
                zone=zone_id,
                where=room_deck.where,
            )
        )
    except _Refused as refusal:
        return Reject(refusal.reason)
    return builder.transaction(
        name=f"add-deck:{room_deck.id}", label=f"Add {room_deck.title.lower()}"
    )


def build_shared_note(game: Game, table: Table, text: str) -> Transaction | Reject:
    """A note on the room's table carrying ``text``: writing someone shared.

    The note is the room type's own note component, put down in its
    ``pieces_zone``. Notes stack down the right-hand side of that zone, each
    a little below the last, so a new one does not land on an old one.
    """
    room = game.definition.room
    spec = next(
        (p for p in game.definition.components.pieces if p.kind is PieceKind.NOTE),
        None,
    )
    if room is None or spec is None:
        return Reject("This room has no notes to write on.")
    zone = table.zones.get(room.pieces_zone)
    if zone is None or not isinstance(zone.geometry, Rect):
        return Reject("This room has nowhere to put a note.")
    rect = zone.geometry
    width = spec.width or 160.0
    height = spec.height or 128.0
    already = sum(
        1 for piece in table.pieces_in_zone(zone.id) if piece.kind is PieceKind.NOTE
    )
    piece_id = new_op_id()
    return Transaction(
        steps=(
            Spawn(
                component_id=spec.id,
                kind=spec.kind,
                zone_id=zone.id,
                piece_ids=(piece_id,),
            ),
            Move(
                piece_id=piece_id,
                x=rect.x + rect.width - width / 2 - 40 - (already // 6) * 40,
                y=rect.y + height / 2 + 40 + (already % 6) * 60,
            ),
            SetText(piece_id=piece_id, text=text),
        ),
        name=f"note:{spec.id}",
        label="Share writing",
    )


__all__ = [
    "ADDED_DECK_PREFIX",
    "MAX_ADDED_DECKS",
    "build_add_deck",
    "build_add_piece",
    "build_shared_note",
    "may_use_facilitator_button",
    "Scope",
    "SetupFailedError",
    "build_activity_start",
    "scope_of",
    "announcement",
    "build_macro",
    "build_seat",
    "build_table",
    "seat_order",
    "seat_zone_id",
]
