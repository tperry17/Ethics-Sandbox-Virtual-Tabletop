from _model_support import (
    DECK,
    FACILITATOR,
    FACILITATOR_TRAY,
    HAND_A,
    PUBLIC_TABLE,
    SEAT_A,
    SEAT_B,
    build_sample_table,
)

from sandbox.model.types import PieceKind
from sandbox.model.visibility import entitled_to_face, project


def test_public_zone_is_visible_to_everyone_including_a_spectator() -> None:
    table = build_sample_table(deck_size=1)
    card = table.pieces["card-0"]
    card.zone_id = PUBLIC_TABLE
    card.face_up = True

    for viewer in (SEAT_A, SEAT_B, FACILITATOR, None):
        view = project(table, viewer)
        viewed = next(p for p in view.pieces if p.id == "card-0")
        assert viewed.component_id == card.component_id
        assert viewed.face_up is True


def test_hidden_zone_hides_the_face_from_everyone_even_if_flagged_face_up() -> None:
    table = build_sample_table(deck_size=1)
    # A face_up=True piece sitting in a hidden zone would be a bug elsewhere -
    # project() must not trust it and must hide the card regardless.
    table.pieces["card-0"].face_up = True

    for viewer in (SEAT_A, SEAT_B, FACILITATOR, None):
        view = project(table, viewer)
        viewed = next(p for p in view.pieces if p.id == "card-0")
        assert viewed.component_id is None
        assert viewed.face_up is False


def test_private_hand_is_visible_only_to_its_owner() -> None:
    table = build_sample_table(deck_size=1)
    card = table.pieces["card-0"]
    card.zone_id = HAND_A
    card.face_up = True

    owner_view = project(table, SEAT_A)
    stranger_view = project(table, SEAT_B)
    facilitator_view = project(table, FACILITATOR)
    spectator_view = project(table, None)

    owner_card = next(p for p in owner_view.pieces if p.id == "card-0")
    assert owner_card.component_id == card.component_id
    for view in (stranger_view, facilitator_view, spectator_view):
        viewed = next(p for p in view.pieces if p.id == "card-0")
        assert viewed.component_id is None
        assert viewed.face_up is False


def test_facilitator_only_zone_is_visible_to_the_facilitator_and_its_owner() -> None:
    table = build_sample_table(deck_size=1)
    card = table.pieces["card-0"]
    card.zone_id = FACILITATOR_TRAY
    card.face_up = True

    assert project(table, FACILITATOR).pieces[0].component_id == card.component_id
    assert project(table, SEAT_A).pieces[0].component_id is None
    assert project(table, SEAT_B).pieces[0].component_id is None


def test_explicit_reveal_overrides_an_otherwise_private_zone() -> None:
    table = build_sample_table(deck_size=1)
    card = table.pieces["card-0"]
    card.zone_id = HAND_A
    card.face_up = True
    card.revealed_to = frozenset({SEAT_B})

    revealed_to_view = project(table, SEAT_B)
    revealed_card = next(p for p in revealed_to_view.pieces if p.id == "card-0")
    assert revealed_card.component_id == card.component_id

    still_hidden_view = project(table, FACILITATOR)
    hidden_card = next(p for p in still_hidden_view.pieces if p.id == "card-0")
    assert hidden_card.component_id is None


def test_a_face_down_piece_in_a_public_zone_shows_no_face() -> None:
    table = build_sample_table(deck_size=1)
    card = table.pieces["card-0"]
    card.zone_id = PUBLIC_TABLE
    card.face_up = False

    view = project(table, SEAT_A)
    viewed = next(p for p in view.pieces if p.id == "card-0")

    # The viewer is entitled to the face, but the piece itself is face-down.
    assert viewed.face_up is False
    assert viewed.component_id is None


def test_entitled_to_face_matches_project_for_every_combination() -> None:
    table = build_sample_table(deck_size=1)
    zones = table.zones.values()
    piece = table.pieces["card-0"]
    viewers = [SEAT_A, SEAT_B, FACILITATOR, None]

    for zone in zones:
        piece.zone_id = zone.id
        for viewer in viewers:
            expected = entitled_to_face(table, piece, zone, viewer)
            view = project(table, viewer)
            viewed = next(p for p in view.pieces if p.id == piece.id)
            assert (viewed.component_id is not None) == expected


def test_project_never_returns_zone_or_seat_data_beyond_what_is_defined() -> None:
    table = build_sample_table(deck_size=0)

    view = project(table, SEAT_A)

    assert {zone.id for zone in view.zones} == set(table.zones)
    assert {seat.id for seat in view.seats} == set(table.seats)


def test_project_of_deck_hides_component_id_but_reports_the_pile() -> None:
    table = build_sample_table(deck_size=6)

    view = project(table, SEAT_A)

    deck_pieces = [p for p in view.pieces if p.zone_id == DECK]
    assert len(deck_pieces) == 6
    assert all(p.component_id is None for p in deck_pieces)


def test_a_tile_shows_its_component_either_way_up_in_a_public_zone() -> None:
    table = build_sample_table(deck_size=1)
    tile = table.pieces["card-0"]
    tile.kind = PieceKind.TILE
    tile.zone_id = PUBLIC_TABLE
    tile.face_up = False

    for viewer in (SEAT_A, SEAT_B, FACILITATOR, None):
        viewed = next(p for p in project(table, viewer).pieces if p.id == "card-0")
        assert viewed.component_id == tile.component_id
        assert viewed.face_up is False


def test_a_tile_is_still_hidden_in_a_hidden_zone_and_private_in_a_hand() -> None:
    table = build_sample_table(deck_size=1)
    tile = table.pieces["card-0"]
    tile.kind = PieceKind.TILE
    tile.face_up = False

    for viewer in (SEAT_A, SEAT_B, FACILITATOR, None):
        viewed = next(p for p in project(table, viewer).pieces if p.id == "card-0")
        assert viewed.component_id is None

    tile.zone_id = HAND_A
    assert entitled_to_face(table, tile, table.zones[HAND_A], SEAT_A)
    assert not entitled_to_face(table, tile, table.zones[HAND_A], SEAT_B)
