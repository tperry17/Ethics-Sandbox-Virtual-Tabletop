"""HTTP routes that game definitions add: previews, images, and starting one."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from _db_support import make_test_engine
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
    response = client.get("/games/two-doors/preview")

    assert response.status_code == 200
    assert "The two doors" in response.text
    assert "Hand · Second seat" in response.text
    for card in GAMES["two-doors"].decks["doors"]:
        assert card.face.title is not None
        assert card.face.title not in response.text
    assert response.text.count('class="table-picture__piece') == 6


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
        "/content/exercises/two-doors/cards.csv",
        "/content/exercises/value-cards-trading/cards.csv",
        "/content/decks/value-cards/cards.csv",
        "/content/exercises/democracy-simulation/roles.csv",
        "/content/exercises/democracy-simulation/elite_sheets.csv",
        "/content/../pyproject.toml",
        "/content/%2e%2e/pyproject.toml",
        "/content/exercises/two-doors/images/README.md",
    ],
)
def test_nothing_but_images_is_served_from_content(
    client: TestClient, path: str
) -> None:
    assert client.get(path).status_code == 404


def test_the_start_page_offers_an_unlisted_game_only_when_asked(
    client: TestClient,
) -> None:
    assert "Two Doors" not in client.get("/start").text

    asked = client.get("/start?game=two-doors").text

    assert "Two Doors" in asked
    assert 'value="two-doors" required checked' in asked


def test_a_two_doors_room_starts_set_up(client: TestClient) -> None:
    response = client.post(
        "/start", data={"game_slug": "two-doors", "display_name": "Ines"}
    )
    assert response.status_code == 303

    table_page = client.get(response.headers["location"])

    assert table_page.status_code == 200
    assert "<title>Two Doors ·" in table_page.text


def test_an_exercise_without_a_definition_keeps_its_drawn_preview(
    client: TestClient,
) -> None:
    page = client.get("/exercises/democracy-simulation").text

    assert "table-picture" not in page
    assert "zone-grid" in page


def test_the_value_cards_deck_page_shows_every_printed_card(
    client: TestClient,
) -> None:
    page = client.get("/exercises/value-cards-trading/deck").text

    assert page.count('class="deck-card ') == 36
    assert "deck-card--sidebar" in page
    assert "/content/decks/value-cards/images/Community.png" in page


def test_an_exercise_without_a_deck_has_no_deck_page(client: TestClient) -> None:
    assert client.get("/exercises/democracy-simulation/deck").status_code == 404
