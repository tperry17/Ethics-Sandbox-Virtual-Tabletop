from fastapi.testclient import TestClient

from sandbox.web.app import app


def test_home_page() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Ethics Sandbox" in response.text


def test_styleguide_renders_design_system() -> None:
    response = TestClient(app).get("/styleguide")

    assert response.status_code == 200
    assert "A quiet room for consequential questions" in response.text
    assert "CARD READABILITY CHECK" in response.text
    assert "button--destructive" in response.text
    assert "zone--private" in response.text
