"""HTTP routes that game definitions add: previews, images, and starting one."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from _db_support import make_test_engine
from _room_support import start_room
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from sandbox.games import GAMES
from sandbox.web.app import app, get_session


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = make_test_engine()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_session() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app, follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_the_preview_draws_the_table_after_setup_without_a_single_face(
    client: TestClient,
) -> None:
    response = client.get("/games/pairs/preview")

    assert response.status_code == 200
    assert "Pairs caught" in response.text
    assert "Hand · Second seat" in response.text
    for card in GAMES["pairs"].decks["cards"]:
        assert card.face.title is not None
        assert card.face.title not in response.text
    assert response.text.count('class="table-picture__piece') == 8


def test_an_unknown_games_preview_is_not_found(client: TestClient) -> None:
    assert client.get("/games/nothing/preview").status_code == 404


def test_a_card_image_is_served(client: TestClient) -> None:
    response = client.get(
        "/content/exercises/value-cards-trading/images/equal-standing.png"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


@pytest.mark.parametrize(
    "path",
    [
        "/content/exercises/pairs/cards.csv",
        "/content/exercises/value-cards-trading/cards.csv",
        "/content/decks/value-cards/cards.csv",
        "/content/exercises/democracy-simulation/roles.csv",
        "/content/exercises/democracy-simulation/elite_sheets.csv",
        "/content/exercises/democracy-simulation/role_cards.csv",
        "/content/exercises/democracy-simulation/sheet_cards.csv",
        "/content/../pyproject.toml",
        "/content/%2e%2e/pyproject.toml",
        "/content/exercises/pairs/images/README.md",
    ],
)
def test_nothing_but_images_is_served_from_content(
    client: TestClient, path: str
) -> None:
    assert client.get(path).status_code == 404


def test_there_is_no_start_page(client: TestClient) -> None:
    assert client.get("/start").status_code in (404, 405)
    assert client.post("/start", data={"display_name": "Ines"}).status_code in (
        404,
        405,
    )


def test_only_a_kind_of_room_can_be_opened(client: TestClient) -> None:
    for kind in ("pairs", "value-cards-trading", "nothing-at-all"):
        assert client.post("/rooms", data={"kind": kind}).status_code == 404


def test_the_test_room_offers_only_its_own_activities(client: TestClient) -> None:
    response = start_room(client, data={"display_name": "Ines"}, kind="test-room")
    assert response.status_code == 303

    table_page = client.get(response.headers["location"])

    assert table_page.status_code == 200
    assert "<title>Test room ·" in table_page.text


def test_the_democracy_simulation_page_draws_its_table_from_its_definition(
    client: TestClient,
) -> None:
    page = client.get("/exercises/democracy-simulation").text

    assert "table-picture" in page
    assert client.get("/games/democracy-simulation/preview").status_code == 200


def test_the_value_cards_deck_page_shows_every_printed_card(
    client: TestClient,
) -> None:
    page = client.get("/exercises/value-cards-trading/deck").text

    assert page.count('class="deck-card ') == 36
    assert "deck-card--sidebar" in page
    assert "/content/decks/value-cards/images/Community.png" in page


def test_an_exercise_without_a_deck_has_no_deck_page(client: TestClient) -> None:
    assert client.get("/exercises/hooked/deck").status_code == 404


def test_the_public_deck_page_never_prints_a_private_deck(
    client: TestClient,
) -> None:
    page = client.get("/exercises/democracy-simulation/deck").text

    # The invitations are given out before the session; the role cards and
    # the elite sheets are private for the whole of it.
    assert page.count('class="deck-card ') == 4
    assert "Town meeting!" in page
    assert "Memorandum prepared for" not in page
    assert "You live by the river" not in page
