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
    build_activity_start,
    build_add_piece,
    build_remove_deck,
)
from sandbox.games.loader import GAMES_ROOT, GameDefinitionError, load_game
from sandbox.model import (
    AddZone,
    Grab,
    JoinActivity,
    Layout,
    MoveToZone,
    Ok,
    OpenActivity,
    Rect,
    Reject,
    RemoveZone,
    ResetTable,
    Table,
    Transaction,
    Visibility,
    ZoneKind,
    piece_actions,
    project,
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
    assert zone.label == "Sidebar 2"
    assert zone.geometry == Rect(x=780, y=340, width=240, height=320)
    assert _groups(table, zone_id) == ["Sidebar"] * 18
    assert not any(piece.face_up for piece in table.pieces_in_zone(zone_id))
    # The base piles are untouched.
    assert len(table.pieces_in_zone("sidebar")) == 18
    assert len(table.pieces_in_zone("deck")) == 18


def test_an_added_deck_is_centred_where_it_was_put_down() -> None:
    # The table has no edge: a pile put down beyond the table zone's outline
    # stays there rather than being pulled back inside it.
    table = seated(ROOM, 1)

    zone_id = _add(table, "core-deck", "seat-1", x=-500, y=5000)

    assert table.zones[zone_id].geometry == Rect(x=-620, y=4840, width=240, height=320)
    assert _groups(table, zone_id) == ["Deck"] * 18


def test_an_added_deck_shuffles_and_deals_like_any_deck() -> None:
    table = seated(ROOM, 3)
    zone_id = _add(table, "core-deck", "seat-2")
    top = table.pieces_in_zone(zone_id)[-1]

    labels = {entry.label for entry in piece_actions(table, top.id, "seat-2")}

    assert "Shuffle the deck" in labels
    assert "3 cards each" in labels


def test_added_decks_are_numbered_after_the_rooms_own() -> None:
    table = seated(ROOM, 1)
    second = _add(table, "sidebar-deck", "seat-1")
    third = _add(table, "sidebar-deck", "seat-1")
    core = _add(table, "core-deck", "seat-1")
    labels = {zone_id: table.zones[zone_id].label for zone_id in (second, third, core)}
    assert labels == {second: "Sidebar 2", third: "Sidebar 3", core: "Core deck 2"}

    # A freed number is used again.
    removed = build_remove_deck(table, second)
    assert isinstance(removed, Transaction)
    assert isinstance(run_op(table, "seat-1", removed), Ok)
    again = _add(table, "sidebar-deck", "seat-1")
    assert table.zones[again].label == "Sidebar 2"


def test_the_table_holds_only_so_many_added_decks() -> None:
    assert MAX_ADDED_DECKS == 15
    table = seated(ROOM, 1)
    for _ in range(MAX_ADDED_DECKS):
        _add(table, "core-deck", "seat-1")

    refused = build_add_piece(ROOM, table, "core-deck", 800, 450)

    assert isinstance(refused, Reject)
    assert "reset the table" in refused.reason


def _move(table: Table, piece_id: str, zone_id: str) -> None:
    moved = run_op(table, "seat-1", MoveToZone(piece_id=piece_id, zone_id=zone_id))
    assert isinstance(moved, Ok), moved


def test_collect_puts_each_card_back_in_its_own_pile() -> None:
    table = seated(ROOM, 2)
    added = _add(table, "sidebar-deck", "seat-1")
    # Mix them up: a sidebar card into the core deck, a core card into a
    # hand, and the added pile's cards into the base sidebar, a hand and
    # onto the table.
    _move(table, table.pieces_in_zone("sidebar")[-1].id, "deck")
    _move(table, table.pieces_in_zone("deck")[0].id, "hand-seat-2")
    strays = table.pieces_in_zone(added)[-3:]
    for piece, zone_id in zip(strays, ("sidebar", "hand-seat-2", "table"), strict=True):
        _move(table, piece.id, zone_id)

    assert isinstance(press(ROOM, table, "collect", "seat-2"), Ok)

    assert _groups(table, "deck") == ["Deck"] * 18
    assert _groups(table, "sidebar") == ["Sidebar"] * 18
    assert _groups(table, added) == ["Sidebar"] * 18
    assert {piece.id for piece in strays} <= {
        piece.id for piece in table.pieces_in_zone(added)
    }
    assert table.pieces_in_zone("hand-seat-2") == []
    assert table.pieces_in_zone("table") == []


def test_collect_leaves_a_running_activitys_cards_alone() -> None:
    table = seated(ROOM, 3)
    trading = GAMES["value-cards-trading"]
    meta = trading.definition.meta
    opened = OpenActivity(
        kind=meta.slug, title=meta.title, min_players=3, max_players=3
    )
    assert isinstance(run_op(table, "seat-1", opened), Ok)
    activity_id = next(reversed(table.activities))
    for seat in ("seat-2", "seat-3"):
        assert isinstance(run_op(table, seat, JoinActivity(activity_id)), Ok)
    started = build_activity_start(trading, table, "seat-1", activity_id)
    assert isinstance(started, Transaction), started
    assert isinstance(run_op(table, "seat-1", started), Ok)
    zones = table.activities[activity_id].zones
    before = {zone: len(table.pieces_in_zone(zone)) for zone in zones}
    # The activity's own deck and sidebar, 18 each.
    assert sum(before.values()) == 36

    assert isinstance(press(ROOM, table, "collect", "seat-2"), Ok)

    assert {zone: len(table.pieces_in_zone(zone)) for zone in zones} == before
    assert len(table.pieces_in_zone("deck")) == 18
    assert len(table.pieces_in_zone("sidebar")) == 18


def test_the_rooms_reset_leaves_a_running_activitys_cards_alone() -> None:
    """Anyone may reset the room, but an activity's cards are its players'."""
    table = seated(ROOM, 3)
    trading = GAMES["value-cards-trading"]
    meta = trading.definition.meta
    opened = OpenActivity(
        kind=meta.slug, title=meta.title, min_players=3, max_players=3
    )
    assert isinstance(run_op(table, "seat-1", opened), Ok)
    activity_id = next(reversed(table.activities))
    for seat in ("seat-2", "seat-3"):
        assert isinstance(run_op(table, seat, JoinActivity(activity_id)), Ok)
    started = build_activity_start(trading, table, "seat-1", activity_id)
    assert isinstance(started, Transaction), started
    assert isinstance(run_op(table, "seat-1", started), Ok)
    zones = table.activities[activity_id].zones
    before = {
        zone: {piece.id for piece in table.pieces_in_zone(zone)} for zone in zones
    }
    assert isinstance(press(ROOM, table, "deal", "seat-2"), Ok)

    assert isinstance(press(ROOM, table, "reset", "seat-2"), Ok)

    after = {zone: {piece.id for piece in table.pieces_in_zone(zone)} for zone in zones}
    assert after == before
    assert table.activities[activity_id].status == "running"
    assert table.pieces_in_zone("hand-seat-2") == []
    assert len(table.pieces_in_zone("deck")) == 18
    assert len(table.pieces_in_zone("sidebar")) == 18


@pytest.mark.parametrize(
    ("macro_id", "pile", "group", "other"),
    [
        ("deal", "deck", "Deck", "sidebar"),
        ("deal_sidebar", "sidebar", "Sidebar", "deck"),
    ],
)
def test_anyone_can_deal_from_either_pile(
    macro_id: str, pile: str, group: str, other: str
) -> None:
    table = seated(ROOM, 3)  # seat-2 is not the facilitator

    assert isinstance(press(ROOM, table, macro_id, "seat-2"), Ok)

    for seat in ("seat-1", "seat-2", "seat-3"):
        assert _groups(table, f"hand-{seat}") == [group] * 3
    assert len(table.pieces_in_zone(pile)) == 9
    assert len(table.pieces_in_zone(other)) == 18
    # Each reads their own three and nobody else's.
    view = project(table, "seat-2")
    faces = {
        piece.zone_id: piece.component_id is not None
        for piece in view.pieces
        if piece.zone_id.startswith("hand-")
    }
    assert faces == {"hand-seat-1": False, "hand-seat-2": True, "hand-seat-3": False}


# -- removing an added deck ----------------------------------------------------


def test_anyone_can_remove_an_added_deck_with_every_card_from_it() -> None:
    table = seated(ROOM, 3)
    added = _add(table, "core-deck", "seat-1")
    # One of its cards has gone to someone else's hand, one onto the table.
    pile = table.pieces_in_zone(added)
    _move(table, pile[-1].id, "hand-seat-3")
    _move(table, pile[-2].id, "table")
    others = {piece.id for piece in table.pieces.values()} - {p.id for p in pile}

    removed = build_remove_deck(table, added)
    assert isinstance(removed, Transaction), removed
    assert isinstance(run_op(table, "seat-2", removed), Ok)

    assert added not in table.zones
    assert set(table.pieces) == others
    assert len(table.pieces_in_zone("deck")) == 18
    assert len(table.pieces_in_zone("sidebar")) == 18


def test_an_emptied_added_deck_can_still_be_removed() -> None:
    table = seated(ROOM, 2)
    added = _add(table, "core-deck", "seat-1")
    for piece in table.pieces_in_zone(added):
        _move(table, piece.id, "table")

    removed = build_remove_deck(table, added)
    assert isinstance(removed, Transaction), removed
    assert isinstance(run_op(table, "seat-2", removed), Ok)

    assert added not in table.zones
    assert table.pieces_in_zone("table") == []


def test_the_rooms_own_piles_are_not_removed_as_decks() -> None:
    table = seated(ROOM, 1)

    for zone_id in ("deck", "sidebar", "table", "nowhere"):
        assert isinstance(build_remove_deck(table, zone_id), Reject)


def test_a_deck_is_not_removed_while_someone_holds_one_of_its_cards() -> None:
    table = seated(ROOM, 2)
    added = _add(table, "core-deck", "seat-1")
    card = table.pieces_in_zone(added)[-1]
    assert isinstance(run_op(table, "seat-2", Grab(piece_id=card.id)), Ok)

    refused = build_remove_deck(table, added)

    assert isinstance(refused, Reject)
    assert "holding" in refused.reason


def test_a_card_from_an_added_deck_offers_to_remove_it_by_its_pile_alone() -> None:
    """The home pile is never sent: a face-down card does not say its group."""
    table = seated(ROOM, 1)
    added = _add(table, "sidebar-deck", "seat-1")
    view = project(table, "seat-1")
    shown = [piece for piece in view.pieces if piece.zone_id == added]
    assert shown
    assert all("home" not in str(piece) for piece in shown)


def test_resetting_the_table_takes_the_added_decks_away() -> None:
    table = seated(ROOM, 1)
    added = {_add(table, "core-deck", "seat-1"), _add(table, "sidebar-deck", "seat-1")}

    assert isinstance(press(ROOM, table, "reset"), Ok)

    assert not added & set(table.zones)
    assert {"table", "deck", "sidebar", "hand-seat-1"} <= set(table.zones)


def test_anyone_may_reset_the_room_which_lays_it_out_again() -> None:
    """Reset is the room's one way back to the start, and it is anyone's."""
    table = seated(ROOM, 2)
    assert not table.is_facilitator("seat-2")
    added = _add(table, "core-deck", "seat-2")
    assert isinstance(press(ROOM, table, "deal", seat="seat-2"), Ok)
    assert table.pieces_in_zone("hand-seat-2")

    assert isinstance(press(ROOM, table, "reset", seat="seat-2"), Ok)

    assert added not in table.zones
    assert table.pieces_in_zone("hand-seat-1") == []
    assert table.pieces_in_zone("hand-seat-2") == []
    assert len(table.pieces_in_zone("deck")) == 18
    assert len(table.pieces_in_zone("sidebar")) == 18


def test_resetting_the_table_directly_is_still_the_facilitators() -> None:
    """Only the room's own button acts for the room; the bare operation does not."""
    table = seated(ROOM, 2)

    outcome = run_op(table, "seat-2", ResetTable())

    assert outcome == Reject("Only the facilitator may reset the table.")


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
