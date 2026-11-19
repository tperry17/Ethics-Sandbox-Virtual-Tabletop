"""Finding game directories and loading each into a ``Game``.

A game is a directory under ``sandbox/games/`` holding a ``game.yaml``, an
``__init__.py`` so it can carry Python, and optionally a ``rules.py`` with
``@macro`` and ``@hook`` functions. Its editable text - deck rows,
facilitation prompts - is CSV under ``content/``, named from the YAML.

Loading checks more than the schema can: that every zone, deck and
component a step names exists, that each ``python:`` macro has a function
and each function a macro, that deck keys are unique and image files are
there. A definition that fails any of it does not load, and the error says
which file and what is wrong.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import yaml
from pydantic import ValidationError

from sandbox.content_loading import CONTENT_ROOT, read_rows
from sandbox.games.definition import (
    ANNOUNCE_FIELDS,
    CollectStep,
    DealStep,
    DrawStep,
    FlipStep,
    GameDefinition,
    ResetZoneStep,
    SetupStep,
    ShuffleStep,
    SpawnDeckStep,
    SpawnStep,
    Step,
    announce_fields,
)
from sandbox.games.hatch import (
    HOOK_ATTRIBUTE,
    MACRO_ATTRIBUTE,
    GameFunction,
    Moment,
)

GAMES_ROOT = Path(__file__).resolve().parent
DEFINITION_FILE = "game.yaml"
RULES_MODULE = "rules"
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"})


class GameDefinitionError(Exception):
    """A game definition that cannot be used, and why, in a readable sentence."""


@dataclass(frozen=True)
class Face:
    """What one component looks like face up. The web layer sends this on."""

    title: str | None = None
    body: str | None = None
    folio: str | None = None
    image: str | None = None
    face_image: str | None = None
    group: str | None = None
    badge: str | None = None
    tint_index: int | None = None
    width: float | None = None
    height: float | None = None


@dataclass(frozen=True)
class Card:
    """One row of a deck: its component id, its face, and every column."""

    component_id: str
    deck_id: str
    face: Face
    fields: dict[str, str]


@dataclass(frozen=True)
class Prompt:
    """A facilitation question; ``group`` is an optional heading it sits under."""

    id: str
    text: str
    group: str | None = None


@dataclass(frozen=True)
class Button:
    """What one macro's button says, from the game's buttons CSV."""

    label: str
    hint: str | None
    confirm: str | None
    announce: str


@dataclass(frozen=True)
class PairOutcome:
    """What happens when one table chooses ``ours`` and its partner ``theirs``."""

    ours: str
    theirs: str
    text: str


@dataclass(frozen=True)
class Game:
    """A loaded, checked game definition and everything it names."""

    definition: GameDefinition
    directory: Path
    decks: dict[str, tuple[Card, ...]]
    prompts: tuple[Prompt, ...]
    buttons: dict[str, Button]
    pair_outcomes: tuple[PairOutcome, ...] = ()
    macro_functions: dict[str, GameFunction] = field(default_factory=dict)
    hooks: dict[Moment, tuple[GameFunction, ...]] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return self.definition.meta.slug

    @property
    def title(self) -> str:
        return self.definition.meta.title

    @property
    def per_seat_zones(self) -> frozenset[str]:
        return frozenset(zone.id for zone in self.definition.zones if zone.per_seat)

    def cards(self) -> dict[str, dict[str, str]]:
        """Every column of every deck row, keyed by component id."""
        return {
            card.component_id: card.fields
            for cards in self.decks.values()
            for card in cards
        }

    def faces(self) -> dict[str, Face]:
        """Every component's face, keyed by component id."""
        faces: dict[str, Face] = {}
        for cards in self.decks.values():
            for card in cards:
                faces[card.component_id] = card.face
        for piece in self.definition.components.pieces:
            faces[piece.id] = Face(
                title=piece.title,
                body=piece.body,
                tint_index=piece.tint_index,
                width=piece.width,
                height=piece.height,
            )
        return faces


def card_component_id(deck_id: str, key: str) -> str:
    """``doors`` and ``Keep the promise`` -> ``doors:keep-the-promise``."""
    slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")
    return f"{deck_id}:{slug}"


def _content_path(root: Path, relative: str, *, what: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise GameDefinitionError(f"{what} {relative!r} is outside content/.")
    if not path.is_file():
        raise GameDefinitionError(f"{what} content/{relative} does not exist.")
    return path


def image_url(path: Path, root: Path = CONTENT_ROOT) -> str:
    """The URL the content route serves ``path`` at."""
    return "/content/" + path.relative_to(root.resolve()).as_posix()


def _cell(row: dict[str, str], column: str | None) -> str | None:
    if column is None:
        return None
    value = row[column].strip()
    return value or None


def _load_deck(
    definition: GameDefinition, deck_index: int, root: Path
) -> tuple[Card, ...]:
    deck = definition.components.decks[deck_index]
    source = _content_path(root, deck.source, what=f"Deck {deck.id!r}'s source")
    rows = read_rows(deck.source, root=root)
    if not rows:
        raise GameDefinitionError(f"Deck {deck.id!r} (content/{deck.source}) is empty.")
    named = [
        deck.key,
        deck.title,
        deck.body,
        deck.folio,
        deck.image,
        deck.face_image,
        deck.group,
        deck.badge,
    ]
    for column in named:
        if column is not None and column not in rows[0]:
            raise GameDefinitionError(
                f"Deck {deck.id!r} names a column {column!r} that "
                f"content/{deck.source} does not have."
            )

    cards: list[Card] = []
    seen: dict[str, int] = {}
    for line, row in enumerate(rows, start=2):
        key = row[deck.key].strip()
        if not key:
            raise GameDefinitionError(
                f"content/{deck.source} line {line} has an empty {deck.key!r}."
            )
        component_id = card_component_id(deck.id, key)
        if component_id in seen:
            raise GameDefinitionError(
                f"content/{deck.source} lines {seen[component_id]} and {line} "
                f"both make the card {component_id!r}; {deck.key!r} must be unique."
            )
        seen[component_id] = line

        image = None
        if deck.image is not None and row[deck.image].strip():
            file = source.parent / "images" / row[deck.image].strip()
            if file.suffix.lower() not in IMAGE_SUFFIXES or not file.is_file():
                raise GameDefinitionError(
                    f"content/{deck.source} line {line} names an image "
                    f"{row[deck.image].strip()!r} that is not in its images/ folder."
                )
            image = image_url(file.resolve(), root)

        face_image = None
        printed = _cell(row, deck.face_image)
        if printed is not None:
            file = source.parent / "images" / printed
            if file.suffix.lower() not in IMAGE_SUFFIXES or not file.is_file():
                raise GameDefinitionError(
                    f"content/{deck.source} line {line} names a face image "
                    f"{printed!r} that is not in its images/ folder."
                )
            face_image = image_url(file.resolve(), root)

        badge = None
        icon = _cell(row, deck.badge)
        if icon is not None:
            file = source.parent / "images" / "icons" / f"{icon}.png"
            if not file.is_file():
                raise GameDefinitionError(
                    f"content/{deck.source} line {line} names an icon {icon!r} "
                    "that is not in its images/icons/ folder."
                )
            badge = image_url(file.resolve(), root)

        cards.append(
            Card(
                component_id=component_id,
                deck_id=deck.id,
                face=Face(
                    title=_cell(row, deck.title),
                    body=_cell(row, deck.body),
                    folio=_cell(row, deck.folio),
                    image=image,
                    face_image=face_image,
                    group=_cell(row, deck.group),
                    badge=badge,
                    width=deck.width,
                    height=deck.height,
                ),
                fields={name: value for name, value in row.items() if name},
            )
        )
    return tuple(cards)


def _load_prompts(definition: GameDefinition, root: Path) -> tuple[Prompt, ...]:
    if definition.prompts is None:
        return ()
    _content_path(root, definition.prompts.source, what="Prompts")
    rows = read_rows(definition.prompts.source, root=root)
    if rows and not {"id", "text"} <= set(rows[0]):
        raise GameDefinitionError(
            f"content/{definition.prompts.source} needs 'id' and 'text' columns."
        )
    return tuple(
        Prompt(
            id=row["id"].strip(),
            text=row["text"].strip(),
            group=(row.get("outcome") or "").strip() or None,
        )
        for row in rows
    )


def _load_pairing(definition: GameDefinition, root: Path) -> tuple[PairOutcome, ...]:
    if definition.pairing is None:
        return ()
    source = definition.pairing.source
    _content_path(root, source, what="Pairing")
    rows = read_rows(source, root=root)
    if not rows or not {"our_choice", "their_choice", "text"} <= set(rows[0]):
        raise GameDefinitionError(
            f"content/{source} needs 'our_choice', 'their_choice' and 'text' columns."
        )
    return tuple(
        PairOutcome(
            ours=row["our_choice"].strip(),
            theirs=row["their_choice"].strip(),
            text=row["text"].strip(),
        )
        for row in rows
    )


def _load_buttons(definition: GameDefinition, root: Path) -> dict[str, Button]:
    """One row per macro, no more and no fewer."""
    source = definition.buttons.source
    _content_path(root, source, what="Buttons")
    rows = read_rows(source, root=root)
    if not rows or not {"id", "label"} <= set(rows[0]):
        raise GameDefinitionError(f"content/{source} needs 'id' and 'label' columns.")
    buttons: dict[str, Button] = {}
    for line, row in enumerate(rows, start=2):
        macro_id = row["id"].strip()
        label = row["label"].strip()
        if macro_id in buttons:
            raise GameDefinitionError(
                f"content/{source} has two rows for {macro_id!r}."
            )
        if not label:
            raise GameDefinitionError(f"content/{source} line {line} has no label.")
        announce = (row.get("announce") or "").strip() or "{name} pressed “{label}”."
        unknown = announce_fields(announce) - ANNOUNCE_FIELDS
        if unknown:
            raise GameDefinitionError(
                f"content/{source} line {line} announces with {sorted(unknown)}; "
                "use {name} and {label} only."
            )
        buttons[macro_id] = Button(
            label=label,
            hint=(row.get("hint") or "").strip() or None,
            confirm=(row.get("confirm") or "").strip() or None,
            announce=announce,
        )
    macro_ids = {macro.id for macro in definition.macros}
    missing = sorted(macro_ids - set(buttons))
    if missing:
        raise GameDefinitionError(f"content/{source} has no row for {missing}.")
    extra = sorted(set(buttons) - macro_ids)
    if extra:
        raise GameDefinitionError(
            f"content/{source} has rows for {extra}, which game.yaml does not define."
        )
    return buttons


def _check_references(definition: GameDefinition) -> None:
    """Every name a step uses must be something the definition defines."""
    zones = {zone.id: zone for zone in definition.zones}
    decks = {deck.id for deck in definition.components.decks}
    pieces = {piece.id for piece in definition.components.pieces}
    option_ids = {option.id for option in definition.options}

    def zone(name: str, where: str, *, shared: bool = False) -> None:
        spec = zones.get(name)
        if spec is None:
            raise GameDefinitionError(
                f"{where} names a zone {name!r} with no definition."
            )
        if shared and spec.per_seat:
            raise GameDefinitionError(
                f"{where} needs one zone, but {name!r} is a zone every seat has."
            )

    def check(steps: Iterable[Step], where: str, *, in_setup: bool) -> None:
        for step in steps:
            if isinstance(step, SetupStep) and in_setup:
                raise GameDefinitionError(f"{where} cannot run 'setup' inside setup.")
            if isinstance(step, SpawnDeckStep):
                if step.deck not in decks:
                    raise GameDefinitionError(
                        f"{where} spawns an unknown deck {step.deck!r}."
                    )
                for value in step.where.values():
                    for name in announce_fields(value):
                        if name not in option_ids:
                            raise GameDefinitionError(
                                f"{where} filters by {{{name}}}, which is not "
                                "one of the definition's options."
                            )
                zone(step.zone, where)
            elif isinstance(step, SpawnStep):
                if step.component not in pieces:
                    raise GameDefinitionError(
                        f"{where} spawns {step.component!r}, which is not one of "
                        "the pieces under components (decks use spawn_deck)."
                    )
                zone(step.zone, where)
            elif isinstance(step, ShuffleStep | FlipStep | ResetZoneStep):
                zone(step.zone, where)
            elif isinstance(step, DealStep | DrawStep):
                zone(step.from_zone, where, shared=True)
                zone(step.to, where)
            elif isinstance(step, CollectStep):
                zone(step.to, where, shared=True)
                for source in step.from_zones:
                    zone(source, where)

    check(definition.setup, "setup", in_setup=True)
    for macro in definition.macros:
        if macro.steps is not None:
            check(macro.steps, f"Macro {macro.id!r}", in_setup=False)


def _check_filters(
    definition: GameDefinition, decks: dict[str, tuple[Card, ...]]
) -> None:
    """Every column a ``where`` filters on must be one its deck has.

    A ``collect`` names no deck, so its columns must be in at least one.
    """

    def columns_of(deck_id: str) -> set[str]:
        return set(decks[deck_id][0].fields) if decks[deck_id] else set()

    steps = [*definition.setup]
    for macro in definition.macros:
        steps.extend(macro.steps or ())
    filters: list[tuple[str, str, set[str]]] = [
        (f"A spawn_deck of {step.deck!r}", column, columns_of(step.deck))
        for step in steps
        if isinstance(step, SpawnDeckStep)
        for column in step.where
    ]
    every_column = set().union(*(columns_of(deck_id) for deck_id in decks))
    filters += [
        (f"A collect into {step.to!r}", column, every_column)
        for step in steps
        if isinstance(step, CollectStep)
        for column in step.where
    ]
    if definition.room is not None:
        filters += [
            (f"The room's deck {room_deck.id!r}", column, columns_of(room_deck.deck))
            for room_deck in definition.room.decks
            for column in room_deck.where
        ]
    for what, column, columns in filters:
        if column not in columns:
            raise GameDefinitionError(
                f"{what} filters on a column {column!r} that the deck's CSV "
                "does not have."
            )
    for room_deck in definition.room.decks if definition.room else ():
        if not any(
            all(
                card.fields.get(c, "").casefold() == v.casefold()
                for c, v in room_deck.where.items()
            )
            for card in decks[room_deck.deck]
        ):
            raise GameDefinitionError(
                f"The room's deck {room_deck.id!r} would have no cards."
            )


def _import_rules(directory: Path, rules: Path) -> ModuleType:
    """A game's ``rules.py``: as part of this package when it lives here.

    A game directory elsewhere - a test's own fixture - is imported from
    its file under a name of its own.
    """
    if directory.resolve().parent == GAMES_ROOT:
        return importlib.import_module(f"sandbox.games.{directory.name}.{RULES_MODULE}")
    name = f"sandbox_game_{directory.name}_{RULES_MODULE}"
    spec = importlib.util.spec_from_file_location(name, rules)
    if spec is None or spec.loader is None:
        raise GameDefinitionError(f"{directory.name}/rules.py cannot be imported.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_rules(
    directory: Path, definition: GameDefinition
) -> tuple[dict[str, GameFunction], dict[Moment, tuple[GameFunction, ...]]]:
    wanted = {macro.python for macro in definition.macros if macro.python is not None}
    module: ModuleType | None = None
    rules = directory / f"{RULES_MODULE}.py"
    if rules.is_file():
        module = _import_rules(directory, rules)
    macros: dict[str, GameFunction] = {}
    hooks: dict[Moment, list[GameFunction]] = {}
    if module is not None:
        for value in vars(module).values():
            macro_id = getattr(value, MACRO_ATTRIBUTE, None)
            moment = getattr(value, HOOK_ATTRIBUTE, None)
            if isinstance(macro_id, str):
                if macro_id in macros:
                    raise GameDefinitionError(
                        f"{directory.name}/rules.py registers macro {macro_id!r} twice."
                    )
                macros[macro_id] = value
            if isinstance(moment, str):
                hooks.setdefault(moment, []).append(value)  # type: ignore[arg-type]
    missing = sorted(wanted - set(macros))
    if missing:
        raise GameDefinitionError(
            f"{directory.name}/game.yaml names python macro(s) {missing}, "
            f"but {directory.name}/rules.py registers no @macro for them."
        )
    unused = sorted(set(macros) - wanted)
    if unused:
        raise GameDefinitionError(
            f"{directory.name}/rules.py registers @macro {unused}, "
            "but no macro in game.yaml says python: for them."
        )
    return macros, {moment: tuple(found) for moment, found in hooks.items()}


def load_game(directory: Path, content_root: Path = CONTENT_ROOT) -> Game:
    """Load and check the game in ``directory``, or raise ``GameDefinitionError``.

    The CSV files it names are read from ``content_root``: the project's
    ``content/`` folder, or a test's own.
    """
    path = directory / DEFINITION_FILE
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise GameDefinitionError(
            f"{path.name} in {directory.name}/ is not valid YAML: {error}"
        ) from error
    try:
        definition = GameDefinition.model_validate(raw)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in issue['loc']) or 'top level'}: "
            f"{issue['msg']}"
            for issue in error.errors()
        )
        raise GameDefinitionError(f"{directory.name}/game.yaml: {problems}") from error
    try:
        _check_references(definition)
        decks = {
            deck.id: _load_deck(definition, index, content_root)
            for index, deck in enumerate(definition.components.decks)
        }
        _check_filters(definition, decks)
        prompts = _load_prompts(definition, content_root)
        buttons = _load_buttons(definition, content_root)
        pair_outcomes = _load_pairing(definition, content_root)
        macro_functions, hooks = _load_rules(directory, definition)
    except GameDefinitionError as error:
        raise GameDefinitionError(f"{directory.name}: {error}") from error
    return Game(
        definition=definition,
        directory=directory,
        decks=decks,
        prompts=prompts,
        buttons=buttons,
        pair_outcomes=pair_outcomes,
        macro_functions=macro_functions,
        hooks=hooks,
    )


def game_directories(root: Path = GAMES_ROOT) -> list[Path]:
    """Every directory under ``root`` holding a ``game.yaml``, by name."""
    return sorted(
        path.parent for path in root.glob(f"*/{DEFINITION_FILE}") if path.is_file()
    )


def load_games(
    root: Path = GAMES_ROOT, content_root: Path = CONTENT_ROOT
) -> dict[str, Game]:
    """Every game under ``root``, keyed by slug. Raises on the first bad one."""
    games: dict[str, Game] = {}
    for directory in game_directories(root):
        game = load_game(directory, content_root)
        if game.slug in games:
            raise GameDefinitionError(
                f"Two games use the slug {game.slug!r}: "
                f"{games[game.slug].directory.name}/ and {directory.name}/."
            )
        games[game.slug] = game
    return games


__all__ = [
    "Button",
    "Card",
    "DEFINITION_FILE",
    "Face",
    "GAMES_ROOT",
    "Game",
    "GameDefinitionError",
    "Prompt",
    "card_component_id",
    "game_directories",
    "image_url",
    "load_game",
    "load_games",
]
