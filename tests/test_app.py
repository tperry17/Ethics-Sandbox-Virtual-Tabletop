import pytest
from fastapi.testclient import TestClient

from sandbox.games import EXERCISES
from sandbox.web.app import app


def test_home_page() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Ethics Sandbox" in response.text


def test_home_page_lists_exercises() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    for exercise in EXERCISES:
        assert exercise.title in response.text
        assert f"/exercises/{exercise.slug}" in response.text


def test_exercise_detail_page_renders_each_exercise() -> None:
    client = TestClient(app)

    for exercise in EXERCISES:
        response = client.get(f"/exercises/{exercise.slug}")

        assert response.status_code == 200
        assert exercise.title in response.text
        assert exercise.premise in response.text
        for step in exercise.session_shape:
            assert step in response.text


def test_exercise_detail_page_404s_for_unknown_slug() -> None:
    response = TestClient(app).get("/exercises/not-a-real-exercise")

    assert response.status_code == 404


def test_styleguide_renders_design_system() -> None:
    response = TestClient(app).get("/styleguide")

    assert response.status_code == 200
    assert "A quiet room for consequential questions" in response.text
    assert "CARD READABILITY CHECK" in response.text
    assert "button--destructive" in response.text
    assert "zone--private" in response.text
    assert '<a href="/">' in response.text
    assert "scholarly edition" not in response.text


def test_landing_page_links_style_guide_in_footer() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    footer = response.text.split('<footer class="site__footer">', 1)[1]
    assert '<a href="/styleguide">Style guide</a>' in footer
    assert "design system" not in response.text


def test_favicon_is_served_at_the_root_and_linked_from_pages() -> None:
    client = TestClient(app)

    icon = client.get("/favicon.ico")
    assert icon.status_code == 200
    assert icon.content[:4] == b"\x00\x00\x01\x00"

    page = client.get("/")
    for path in ("favicon.ico", "seal-512.png", "apple-touch-icon.png"):
        assert f"/static/icons/{path}" in page.text
        assert client.get(f"/static/icons/{path}").status_code == 200


def test_health_page_names_the_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANDBOX_PUBLIC_URL", "http://192.168.1.20:8000/")
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert "http://192.168.1.20:8000" in response.text


def test_an_unknown_room_says_what_happened_and_what_to_do() -> None:
    response = TestClient(app).get("/exercises/nope", headers={"accept": "text/html"})
    assert response.status_code == 404
    assert "No such exercise." in response.text
    assert "Check the room code" in response.text


def test_json_requests_keep_json_errors() -> None:
    response = TestClient(app).get(
        "/exercises/nope", headers={"accept": "application/json"}
    )
    assert response.status_code == 404
    assert response.json()["detail"]
