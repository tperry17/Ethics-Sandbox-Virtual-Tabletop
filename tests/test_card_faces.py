"""Value Cards are drawn from pictures of the printed cards."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sandbox.games import GAMES
from sandbox.games.loader import GAMES_ROOT, GameDefinitionError, load_game
from sandbox.web.app import app
from sandbox.web.live import component_views


@pytest.mark.parametrize("slug", ["value-cards-room", "value-cards-trading"])
def test_every_value_card_has_its_printed_face(slug: str) -> None:
    cards = GAMES[slug].decks["values"]
    assert len(cards) == 36
    for card in cards:
        title = card.face.title
        assert title is not None
        assert card.face.face_image is not None
        assert card.face.face_image.endswith(f"/images/faces/{title}.jpg")


def test_the_printed_faces_are_served_and_sent_with_the_card() -> None:
    client = TestClient(app)
    views = component_views(GAMES["value-cards-room"])
    for view in views.values():
        if view.face_image is None:
            continue
        response = client.get(view.face_image)
        assert response.status_code == 200, view.face_image
        assert response.headers["content-type"] == "image/jpeg"


def _room_copy(tmp_path: Path, old: str, new: str) -> Path:
    directory = tmp_path / "value_cards_room"
    shutil.copytree(GAMES_ROOT / "value_cards_room", directory)
    path = directory / "game.yaml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    ("new", "message"),
    [
        ("face_image: name", "names a face image 'Community'"),
        ("face_image: nowhere", "names a column 'nowhere'"),
    ],
)
def test_a_face_image_that_is_not_there_is_refused(
    tmp_path: Path, new: str, message: str
) -> None:
    with pytest.raises(GameDefinitionError, match=message):
        load_game(_room_copy(tmp_path, "face_image: face", new))
