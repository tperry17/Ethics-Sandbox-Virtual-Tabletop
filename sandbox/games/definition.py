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
    folder. Every column of a row stays available on the loaded card, for
    pages that need more than the face.
    """

    id: Identifier
    kind: PieceKind = PieceKind.CARD
    source: str = Field(min_length=1)
    key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str | None = None
    folio: str | None = None
    image: str | None = "image"
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


class ZoneSpec(_Strict):
    """A zone, or with ``per_seat`` a zone each seat gets its own copy of.

    A per-seat zone's id on the table is ``<id>-<seat id>`` (``hand-seat-2``),
    its owner is that seat, and each further seat's copy is moved by
    ``step`` from the one before.
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
    """One piece per card of ``deck`` into ``zone``, in a shuffled order."""

    op: Literal["spawn_deck"]
    deck: Identifier
    zone: Identifier


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
    but ``to`` is collected from. Pieces end face up or down as ``face_up``
    says, or as their destination zone leaves them when it is omitted.
    """

    op: Literal["collect"]
    to: Identifier
    kinds: tuple[PieceKind, ...] = ()
    from_zones: tuple[Identifier, ...] = Field(default=(), alias="from")
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


class Buttons(TextSource):
    """What each macro button says, as a CSV.

    Columns: ``id`` (the macro), ``label``, ``hint``, ``confirm`` (asked
    before it runs; give one to anything destructive) and ``announce`` (what
    the table is told, with ``{name}`` for who pressed it and ``{label}``).
    Only ``id`` and ``label`` must be filled in.
    """


class GameDefinition(_Strict):
    """A whole ``game.yaml``."""

    meta: Meta
    components: Components = Components()
    seats: Seats = Seats()
    zones: tuple[ZoneSpec, ...]
    setup: tuple[Step, ...] = ()
    macros: tuple[MacroSpec, ...]
    buttons: Buttons
    prompts: Prompts | None = None

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
        ):
            repeated = duplicates(ids)
            if repeated:
                raise ValueError(f"{what} ids used more than once: {repeated}")
        missing = [
            macro_id
            for macro_id in STANDARD_MACROS
            if macro_id not in {macro.id for macro in self.macros}
        ]
        if missing:
            raise ValueError(f"every exercise needs these macros as well: {missing}")
        return self

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
    "PieceSpec",
    "PlayerRange",
    "Prompts",
    "ResetTableStep",
    "ResetZoneStep",
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
