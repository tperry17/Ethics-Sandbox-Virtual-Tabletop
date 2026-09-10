from fastapi.testclient import TestClient

from sandbox.web.app import app


def test_home_page() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Ethics Sandbox" in response.text
