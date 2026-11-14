"""The shape of an exercise's ``game.yaml``, checked by Pydantic on load.

A game definition says what an exercise is made of and how its table is
arranged: components, seats, zones, the steps that set the table up, and
the macro buttons a facilitator presses. It says nothing about who may see
what beyond each zone's visibility - that is ``sandbox.model``'s to judge.

Wording a person edits routinely does not live here. A deck's cards and an
exercise's facilitation prompts are CSV files under ``content/`` (see
``content/README.md``), named from the YAML by path. What stays in YAML is
structure: ids, geometry, numbers, and the short labels on buttons and
zones.
"""

from __future__ import annotations

import string
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sandbox.model.types import Layout, PieceKind, Visibility, ZoneKind

Identifier = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")]

# Every exercise offers at least these, so a facilitator finds the same
# controls whichever exercise they are running.
STANDARD_MACROS: tuple[str, ...] = (
    "setup",
    "deal",
    "reset",
    "shuffle",
    "collect",
    "clear_ink",
)

# A room type needs fewer: its table may have no deck to deal from.
ROOM_MACROS: tuple[str, ...] = ("setup", "reset", "clear_ink")

ANNOUNCE_FIELDS = frozenset({"name", "label"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class PlayerRange(_Strict):
    min: int = Field(ge=1)
    max: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> PlayerRange:
        if self.min > self.max:
            raise ValueError("players.min is larger than players.max")
        return self


class Meta(_Strict):
    """What the engine needs to know about the exercise as a whole.

    The title is the one piece of display text kept here, because the
    table needs a name even for an exercise the public site does not list.
    A listed exercise's site copy - blurb, premise, the group size as a
    sentence - lives in ``content/site/exercises.csv``, and ``validate-games``
    checks that the two titles agree.
    """

    slug: Identifier
    title: str = Field(min_length=1)
    players: PlayerRange
    duration_minutes: int = Field(ge=1)
    facilitator: Literal["required", "recommended", "optional"]
    listed: bool = True


class DeckSpec(_Strict):
    """A deck whose cards are the rows of a CSV file under ``content/``.

    ``key`` names the column that identifies a card; it becomes part of the
    card's component id, so it must be unique within the deck. ``title``,
    ``body`` and ``folio`` name the columns drawn on the card's face, and
    ``image`` the column naming an image file in the exercise's ``images/``
    folder. ``group`` names a column whose value is the card's group, drawn
    as a frame colour, and ``badge`` one whose value names an icon file
    (``<value>.png``) in ``images/icons/``. Every column of a row stays
    available on the loaded card, for pages that need more than the face.
    ``revealable: false`` makes the deck's cards ones nobody may show to
    anyone, even a person who can read them: the model refuses the reveal,
    and the menu does not offer it. ``locked: true`` lays its cards out
    locked in place; anyone who may move them may unlock them. ``kind:
    tile`` makes them tiles, whose two sides are both public: the back
    shows the picture and the title, at the same size as the front.
    """

    id: Identifier
    kind: PieceKind = PieceKind.CARD
    source: str = Field(min_length=1)
    key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str | None = None
    folio: str | None = None
    image: str | None = "image"
    group: str | None = None
    badge: str | None = None
    revealable: bool = True
    locked: bool = False
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)


class PieceSpec(_Strict):
    """One kind of loose piece: a die, a token, a cube, a meeple, a note."""

    id: Identifier
    kind: PieceKind
    title: str | None = None
    body: str | None = None
    faces: tuple[str, ...] | None = None
    tint_index: int | None = Field(default=None, ge=0)
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _dice_have_faces(self) -> PieceSpec:
        if self.kind is PieceKind.DIE and not self.faces:
            raise ValueError(f"die {self.id!r} needs a non-empty list of faces")
        if self.kind is not PieceKind.DIE and self.faces is not None:
            raise ValueError(f"only a die has faces; {self.id!r} is a {self.kind}")
        return self


class Components(_Strict):
    decks: tuple[DeckSpec, ...] = ()
    pieces: tuple[PieceSpec, ...] = ()


class Seats(_Strict):
    """How seats are named. Seats are created as people sit down.

    ``labels`` names seats in the order they are taken; a seat past the end
    of the list is "Seat N". ``assignment`` records whether roles are
    handed out by the facilitator or chosen by participants; nothing acts on
    it until an exercise with roles needs it.
    """

    labels: tuple[str, ...] = ()
    assignment: Literal["chosen", "assigned"] = "chosen"


class OptionChoice(_Strict):
    id: Identifier
    label: str = Field(min_length=1)


class OptionSpec(_Strict):
    """A named choice made when the activity is started, such as which city.

    Steps may use the chosen value as ``{id}`` in a ``where``, and a rule
    reads it from ``GameContext.options``. The first choice is the default.
    """

    id: Identifier
    label: str = Field(min_length=1)
    choices: tuple[OptionChoice, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _distinct(self) -> OptionSpec:
        ids = [choice.id for choice in self.choices]
        if len(set(ids)) != len(ids):
            raise ValueError(f"option {self.id!r} has a choice listed twice")
        return self


class ZoneSpec(_Strict):
    """A zone, or with ``per_seat`` a zone each seat gets its own copy of.

    A per-seat zone's id on the table is ``<id>-<seat id>`` (``hand-seat-2``),
    its owner is that seat, and each further seat's copy is moved by
    ``step`` from the one before. With ``when``, the zone exists only if
    each named option was given that choice.
    """

    id: Identifier
    kind: ZoneKind
    label: str = Field(min_length=1)
    rect: tuple[float, float, float, float]
    visibility: Visibility
    layout: Layout
    capacity: int | None = Field(default=None, ge=1)
    owner_moves_only: bool = False
    per_seat: bool = False
    step: tuple[float, float] = (0.0, 0.0)
    when: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _owned_visibility_needs_a_seat(self) -> ZoneSpec:
        owned = (Visibility.PRIVATE_TO_OWNER, Visibility.FACILITATOR_ONLY)
        if self.visibility is Visibility.PRIVATE_TO_OWNER and not self.per_seat:
            raise ValueError(
                f"zone {self.id!r} is private_to_owner but not per_seat, "
                "so it has no owner and nobody could ever see into it"
            )
        if self.per_seat and self.visibility not in (*owned, Visibility.PUBLIC):
            raise ValueError(f"per-seat zone {self.id!r} cannot be hidden")
        if self.owner_moves_only and not self.per_seat:
            raise ValueError(
                f"zone {self.id!r} is owner_moves_only but not per_seat, "
                "so it has no owner"
            )
        if self.rect[2] <= 0 or self.rect[3] <= 0:
            raise ValueError(f"zone {self.id!r} needs a positive width and height")
        return self


# -- steps ------------------------------------------------------------------
#
# A step names a zone by its definition id. Naming a per-seat zone means
# every seat's copy of it, in seat order.


class SetupStep(_Strict):
    """Run the definition's ``setup`` steps, and its after-setup hooks, here."""

    op: Literal["setup"]


class SpawnDeckStep(_Strict):
    """One piece per card of ``deck`` into ``zone``, in a shuffled order.

    ``where`` keeps only the rows whose columns equal these values, ignoring
    case; a value may name an option as ``{option-id}``.
    """

    op: Literal["spawn_deck"]
    deck: Identifier
    zone: Identifier
    where: dict[str, str] = Field(default_factory=dict)


class SpawnStep(_Strict):
    """``count`` pieces of one loose component into ``zone``."""

    op: Literal["spawn"]
    component: Identifier
    zone: Identifier
    count: int = Field(default=1, ge=1)


class ShuffleStep(_Strict):
    op: Literal["shuffle"]
    zone: Identifier


class DealStep(_Strict):
    """``count`` pieces to each destination, one round at a time.

    ``face_up`` turns the dealt pieces as they land. Left out, a piece dealt
    into its owner's private hand lands face up - readable by the owner and
    nobody else - and a piece dealt anywhere else stays as it came off the
    pile.
    """

    op: Literal["deal"]
    from_zone: Identifier = Field(alias="from")
    to: Identifier
    count: int = Field(default=1, ge=1)
    face_up: bool | None = None


class DrawStep(_Strict):
    op: Literal["draw"]
    from_zone: Identifier = Field(alias="from")
    to: Identifier
    count: int = Field(default=1, ge=1)
    face_up: bool | None = None


class CollectStep(_Strict):
    """Every piece of the given kinds, from the given zones, into ``to``.

    With no ``kinds`` every kind is collected; with no ``from`` every zone
    but ``to`` is collected from. ``where`` keeps only cards whose deck row
    has these column values, ignoring case, as in ``spawn_deck``: two piles
    of one deck can each take back their own cards. ``own_pile`` sends a
    card added with a pile from the room's Pieces menu back to that pile,
    while it is on the table, rather than to ``to``. Pieces end face up or
    down as ``face_up`` says, or as their destination zone leaves them when
    it is omitted.
    """

    op: Literal["collect"]
    to: Identifier
    kinds: tuple[PieceKind, ...] = ()
    from_zones: tuple[Identifier, ...] = Field(default=(), alias="from")
    where: dict[str, str] = Field(default_factory=dict)
    own_pile: bool = False
    face_up: bool | None = None


class FlipStep(_Strict):
    """Turn every piece in ``zone`` face up or face down."""

    op: Literal["flip"]
    zone: Identifier
    face_up: bool


class ResetTableStep(_Strict):
    """Remove every piece and every ink stroke. Zones and seats stay."""

    op: Literal["reset_table"]


class ResetZoneStep(_Strict):
    op: Literal["reset_zone"]
    zone: Identifier


class ClearInkStep(_Strict):
    """Erase everyone's ink. Only the facilitator may."""

    op: Literal["clear_ink"]


Step = Annotated[
    SetupStep
    | SpawnDeckStep
    | SpawnStep
    | ShuffleStep
    | DealStep
    | DrawStep
    | CollectStep
    | FlipStep
    | ResetTableStep
    | ResetZoneStep
    | ClearInkStep,
    Field(discriminator="op"),
]


class MacroSpec(_Strict):
    """One toolbar button: who may press it, and steps or a ``@macro`` name.

    What the button says - its label, hint, the question asked before it
    runs, and what the table is told afterwards - is in the game's buttons
    CSV, one row per macro id, so it can be edited as a spreadsheet.
    """

    id: Identifier
    who: Literal["facilitator", "anyone"] = "facilitator"
    steps: tuple[Step, ...] | None = None
    python: Identifier | None = None

    @model_validator(mode="after")
    def _one_body(self) -> MacroSpec:
        if (self.steps is None) == (self.python is None):
            raise ValueError(
                f"macro {self.id!r} needs exactly one of 'steps' or 'python'"
            )
        return self


def announce_fields(announce: str) -> set[str]:
    """The ``{fields}`` an announcement uses."""
    return {
        name
        for _text, name, _spec, _conversion in string.Formatter().parse(announce)
        if name is not None
    }


class TextSource(_Strict):
    """A CSV file under the content folder."""

    source: str = Field(min_length=1)


class Prompts(TextSource):
    """Facilitation questions, as a CSV with ``id`` and ``text`` columns."""


class Pairing(TextSource):
    """Tables of a class that may be paired, and what a pair's choices lead to.

    ``source`` is a CSV with ``our_choice``, ``their_choice`` and ``text``
    columns: one row for each choice a table may make against each choice its
    partner may make. ``when`` limits pairing to the options it names (the
    scenario that is about two cities, not the one about one).
    """

    when: dict[str, str] = Field(default_factory=dict)


class Buttons(TextSource):
    """What each macro button says, as a CSV.

    Columns: ``id`` (the macro), ``label``, ``hint``, ``confirm`` (asked
    before it runs; give one to anything destructive) and ``announce`` (what
    the table is told, with ``{name}`` for who pressed it and ``{label}``).
    Only ``id`` and ``label`` must be filled in.
    """


class RoomActivity(_Strict):
    """One activity a room offers: a game, perhaps with some options fixed.

    ``id`` is what the room's toolbar sends to start it. ``options`` fixes
    choices of the game's own options (a scenario, say); the rest are still
    chosen when it starts. ``class_only`` offers it only as a class.
    ``debrief`` lists it under the room's own "Debrief" heading, below the
    activities.
    """

    id: Identifier
    game: Identifier
    title: str | None = None
    options: dict[str, str] = Field(default_factory=dict)
    class_only: bool = False
    debrief: bool = False


class RoomDeck(_Strict):
    """A deck the room's "Pieces" menu can add as a pile of its own.

    ``deck`` names one of the definition's decks and ``where`` keeps only
    some of its rows, as in ``spawn_deck``. The new pile is a zone made like
    ``shaped_like`` - its size, kind, visibility and layout - put down where
    the person is looking, and named ``title``.
    """

    id: Identifier
    title: str = Field(min_length=1)
    deck: Identifier
    where: dict[str, str] = Field(default_factory=dict)
    shaped_like: Identifier


class RoomSpec(_Strict):
    """What makes a definition a room type: one exercise's sandbox.

    ``exercise`` is the catalog slug whose page opens this room;
    ``activities`` are all the room offers, and ``pieces`` are the
    components its "Pieces" menu adds to the table, into ``pieces_zone``.
    ``decks`` are the further piles of cards the same menu can add there.
    """

    exercise: Identifier
    label: str = Field(min_length=1)
    activities: tuple[RoomActivity, ...] = Field(min_length=1)
    pieces: tuple[Identifier, ...] = ()
    decks: tuple[RoomDeck, ...] = ()
    pieces_zone: Identifier = "table"


class GameDefinition(_Strict):
    """A whole ``game.yaml``."""

    meta: Meta
    components: Components = Components()
    seats: Seats = Seats()
    options: tuple[OptionSpec, ...] = ()
    zones: tuple[ZoneSpec, ...]
    setup: tuple[Step, ...] = ()
    macros: tuple[MacroSpec, ...]
    buttons: Buttons
    prompts: Prompts | None = None
    pairing: Pairing | None = None
    room: RoomSpec | None = None

    @model_validator(mode="after")
    def _unique_and_complete(self) -> GameDefinition:
        def duplicates(ids: list[str]) -> list[str]:
            return sorted({value for value in ids if ids.count(value) > 1})

        component_ids = [deck.id for deck in self.components.decks] + [
            piece.id for piece in self.components.pieces
        ]
        for what, ids in (
            ("component", component_ids),
            ("zone", [zone.id for zone in self.zones]),
            ("macro", [macro.id for macro in self.macros]),
            ("option", [option.id for option in self.options]),
        ):
            repeated = duplicates(ids)
            if repeated:
                raise ValueError(f"{what} ids used more than once: {repeated}")
        for zone in self.zones:
            for option_id, choice_id in zone.when.items():
                option = next((o for o in self.options if o.id == option_id), None)
                if option is None or choice_id not in {c.id for c in option.choices}:
                    raise ValueError(
                        f"zone {zone.id!r} is only for {option_id}={choice_id}, "
                        "which is not an option the definition offers"
                    )
        if self.room is not None:
            repeated = duplicates([activity.id for activity in self.room.activities])
            if repeated:
                raise ValueError(f"room activity ids used more than once: {repeated}")
            unknown = sorted(
                set(self.room.pieces) - {piece.id for piece in self.components.pieces}
            )
            if unknown:
                raise ValueError(f"the room's pieces are not pieces: {unknown}")
            if (self.room.pieces or self.room.decks) and self.zone_spec(
                self.room.pieces_zone
            ) is None:
                raise ValueError(
                    f"the room's pieces go into {self.room.pieces_zone!r}, "
                    "which is not one of its zones"
                )
            repeated = duplicates(
                [deck.id for deck in self.room.decks] + list(self.room.pieces)
            )
            if repeated:
                raise ValueError(f"the room's Pieces menu repeats {repeated}")
            for room_deck in self.room.decks:
                if room_deck.deck not in {deck.id for deck in self.components.decks}:
                    raise ValueError(
                        f"the room's deck {room_deck.id!r} names a deck "
                        f"{room_deck.deck!r} that is not one of its components"
                    )
                shape = self.zone_spec(room_deck.shaped_like)
                if shape is None or shape.per_seat:
                    raise ValueError(
                        f"the room's deck {room_deck.id!r} is shaped like "
                        f"{room_deck.shaped_like!r}, which is not a shared zone"
                    )
        missing = [
            macro_id
            for macro_id in (ROOM_MACROS if self.room else STANDARD_MACROS)
            if macro_id not in {macro.id for macro in self.macros}
        ]
        if missing:
            raise ValueError(f"this definition needs these macros as well: {missing}")
        return self

    def default_options(self) -> dict[str, str]:
        """Each option at its first choice."""
        return {option.id: option.choices[0].id for option in self.options}

    def zone_spec(self, zone_id: str) -> ZoneSpec | None:
        return next((zone for zone in self.zones if zone.id == zone_id), None)

    def macro(self, macro_id: str) -> MacroSpec | None:
        return next((macro for macro in self.macros if macro.id == macro_id), None)


__all__ = [
    "ANNOUNCE_FIELDS",
    "Buttons",
    "ClearInkStep",
    "CollectStep",
    "Components",
    "DealStep",
    "DeckSpec",
    "DrawStep",
    "FlipStep",
    "GameDefinition",
    "MacroSpec",
    "Meta",
    "OptionChoice",
    "OptionSpec",
    "PieceSpec",
    "PlayerRange",
    "Prompts",
    "RoomActivity",
    "RoomSpec",
    "ResetTableStep",
    "ResetZoneStep",
    "ROOM_MACROS",
    "STANDARD_MACROS",
    "Seats",
    "SetupStep",
    "ShuffleStep",
    "SpawnDeckStep",
    "SpawnStep",
    "Step",
    "TextSource",
    "announce_fields",
    "ZoneSpec",
]
