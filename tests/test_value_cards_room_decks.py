"""The Value Cards room's two piles, and the further decks its Pieces menu adds."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from _games_support import press, seated

from sandbox.games import GAMES
from sandbox.games.engine import (
    ADDED_DECK_PREFIX,
    MAX_ADDED_DECKS,
    build_add_piece,
)
from sandbox.games.loader import GAMES_ROOT, GameDefinitionError, load_game
from sandbox.model import (
    AddZone,
    Layout,
    MoveToZone,
    Ok,
    OpenActivity,
    Rect,
    Reject,
    RemoveZone,
    Table,
    Transaction,
    Visibility,
    ZoneKind,
    piece_actions,
    run_op,
)

ROOM = GAMES["value-cards-room"]
GROUPS = {card.component_id: card.face.group for card in ROOM.decks["values"]}


def _groups(table: Table, zone_id: str) -> list[str | None]:
    return [GROUPS[piece.component_id] for piece in table.pieces_in_zone(zone_id)]


def _add(table: Table, entry: str, seat: str, x: float = 800, y: float = 450) -> str:
    """Add ``entry`` from the Pieces menu as ``seat``; the new zone's id."""
    before = set(table.zones)
    built = build_add_piece(ROOM, table, entry, x, y)
    assert isinstance(built, Transaction), built
    assert isinstance(run_op(table, seat, built), Ok)
    (zone_id,) = set(table.zones) - before
    return zone_id


def test_the_room_lays_out_the_core_deck_and_the_sidebar_apart() -> None:
    table = seated(ROOM, 1)

    assert _groups(table, "deck") == ["Deck"] * 18
    assert _groups(table, "sidebar") == ["Sidebar"] * 18
    assert table.zones["deck"].label == "Core deck"
    assert table.zones["sidebar"].label == "Sidebar"
    for zone_id in ("deck", "sidebar"):
        assert table.zones[zone_id].visibility is Visibility.HIDDEN
        assert not any(piece.face_up for piece in table.pieces_in_zone(zone_id))


def test_anyone_can_add_a_further_deck_as_a_pile_of_its_own() -> None:
    table = seated(ROOM, 2)  # seat-2 is not the facilitator

    zone_id = _add(table, "sidebar-deck", "seat-2", x=900, y=500)

    zone = table.zones[zone_id]
    assert zone_id.startswith(ADDED_DECK_PREFIX)
    assert (zone.kind, zone.visibility, zone.layout) == (
        ZoneKind.DECK,
        Visibility.HIDDEN,
        Layout.STACK,
    )
    assert zone.label == "Sidebar"
    assert zone.geometry == Rect(x=780, y=340, width=240, height=320)
    assert _groups(table, zone_id) == ["Sidebar"] * 18
    assert not any(piece.face_up for piece in table.pieces_in_zone(zone_id))
    # The base piles are untouched.
    assert len(table.pieces_in_zone("sidebar")) == 18
    assert len(table.pieces_in_zone("deck")) == 18


def test_an_added_deck_stays_on_the_table() -> None:
    table = seated(ROOM, 1)

    zone_id = _add(table, "core-deck", "seat-1", x=-500, y=5000)

    assert table.zones[zone_id].geometry == Rect(x=0, y=580, width=240, height=320)
    assert _groups(table, zone_id) == ["Deck"] * 18


def test_an_added_deck_shuffles_and_deals_like_any_deck() -> None:
    table = seated(ROOM, 3)
    zone_id = _add(table, "core-deck", "seat-2")
    top = table.pieces_in_zone(zone_id)[-1]

    labels = {entry.label for entry in piece_actions(table, top.id, "seat-2")}

    assert "Shuffle the deck" in labels
    assert "3 cards each" in labels


def test_the_table_holds_only_so_many_added_decks() -> None:
    table = seated(ROOM, 1)
    for _ in range(MAX_ADDED_DECKS):
        _add(table, "core-deck", "seat-1")

    refused = build_add_piece(ROOM, table, "core-deck", 800, 450)

    assert isinstance(refused, Reject)
    assert "reset the table" in refused.reason


def test_collect_puts_each_card_back_in_its_own_pile() -> None:
    table = seated(ROOM, 2)
    added = _add(table, "sidebar-deck", "seat-1")
    # Mix them up: a sidebar card into the core deck, a core card into a hand.
    sidebar_card = table.pieces_in_zone("sidebar")[-1]
    core_card = table.pieces_in_zone("deck")[-1]
    for piece_id, zone_id in (
        (sidebar_card.id, "deck"),
        (core_card.id, "hand-seat-2"),
    ):
        assert isinstance(
            run_op(table, "seat-1", MoveToZone(piece_id=piece_id, zone_id=zone_id)),
            Ok,
        )

    assert isinstance(press(ROOM, table, "collect", "seat-2"), Ok)

    assert _groups(table, "deck") == ["Deck"] * 18
    # The sidebar takes back its own 18 and the added deck's 18.
    assert _groups(table, "sidebar") == ["Sidebar"] * 36
    assert table.pieces_in_zone(added) == []
    assert table.pieces_in_zone("hand-seat-2") == []


@pytest.mark.parametrize("macro_id", ["reset", "setup"])
def test_resetting_the_table_takes_the_added_decks_away(macro_id: str) -> None:
    table = seated(ROOM, 1)
    added = {_add(table, "core-deck", "seat-1"), _add(table, "sidebar-deck", "seat-1")}

    assert isinstance(press(ROOM, table, macro_id), Ok)

    assert not added & set(table.zones)
    assert {"table", "deck", "sidebar", "hand-seat-1"} <= set(table.zones)


def test_the_menu_adds_only_the_rooms_own_decks() -> None:
    table = seated(ROOM, 1)

    refused = build_add_piece(ROOM, table, "values", 800, 450)

    assert isinstance(refused, Reject)


# -- removing a zone ---------------------------------------------------------


def _with_spare_zone(table: Table) -> str:
    zone = AddZone(
        zone_id="spare",
        kind=ZoneKind.DECK,
        label="Spare",
        geometry=Rect(x=0, y=0, width=10, height=10),
        visibility=Visibility.PUBLIC,
        layout=Layout.STACK,
    )
    assert isinstance(run_op(table, "seat-1", zone), Ok)
    return zone.zone_id


def test_only_the_facilitator_removes_a_zone() -> None:
    table = seated(ROOM, 2)
    _with_spare_zone(table)

    refused = run_op(table, "seat-2", RemoveZone(zone_id="spare"))
    assert isinstance(refused, Reject)
    assert "facilitator" in refused.reason
    assert isinstance(run_op(table, "seat-1", RemoveZone(zone_id="spare")), Ok)
    assert "spare" not in table.zones


def test_a_zone_with_pieces_in_it_is_not_removed() -> None:
    table = seated(ROOM, 1)

    refused = run_op(table, "seat-1", RemoveZone(zone_id="deck"))

    assert isinstance(refused, Reject)
    assert "still has pieces" in refused.reason


def test_an_activitys_zone_is_not_removed() -> None:
    table = seated(ROOM, 1)
    _with_spare_zone(table)
    opened = OpenActivity(
        kind="value-cards-trading", title="Trading", min_players=3, max_players=3
    )
    assert isinstance(run_op(table, "seat-1", opened), Ok)
    table.activities["activity-1"].zones = ("spare",)

    refused = run_op(table, "seat-1", RemoveZone(zone_id="spare"))

    assert isinstance(refused, Reject)
    assert "belongs to an activity" in refused.reason


# -- what loading checks -----------------------------------------------------


def _room_copy(tmp_path: Path, old: str, new: str) -> Path:
    directory = tmp_path / "value_cards_room"
    shutil.copytree(GAMES_ROOT / "value_cards_room", directory)
    path = directory / "game.yaml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "where: {group: Sidebar}, shaped_like",
            "where: {group: Nothing}, shaped_like",
            "would have no cards",
        ),
        (
            "where: {group: Sidebar}, shaped_like",
            "where: {colour: Sidebar}, shaped_like",
            "column 'colour'",
        ),
        (
            "kinds: [card], where: {group: Deck}",
            "kinds: [card], where: {colour: Deck}",
            "A collect into 'deck' filters on a column 'colour'",
        ),
    ],
)
def test_loading_checks_the_filters(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    with pytest.raises(GameDefinitionError, match=message):
        load_game(_room_copy(tmp_path, old, new))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "deck: values, where: {group: Deck}, shaped_like",
            "deck: tarot, where: {group: Deck}, shaped_like",
            "not one of its components",
        ),
        ("shaped_like: sidebar}", "shaped_like: hand}", "not a shared zone"),
        ("{id: core-deck,", "{id: d6,", "repeats"),
    ],
)
def test_loading_checks_the_room_decks(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    with pytest.raises((GameDefinitionError, ValueError), match=message):
        load_game(_room_copy(tmp_path, old, new))
