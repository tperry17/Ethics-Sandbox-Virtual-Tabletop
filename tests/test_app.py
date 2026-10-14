from fastapi.testclient import TestClient

from sandbox.games import EXERCISES
from sandbox.web.app import app
from sandbox.web.content import PRINCIPLES


def test_home_page() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Ethics Sandbox" in response.text


def test_home_page_lists_exercises_and_principles() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    for exercise in EXERCISES:
        assert exercise.title in response.text
        assert f"/exercises/{exercise.slug}" in response.text
    for principle in PRINCIPLES:
        assert principle.title in response.text


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
