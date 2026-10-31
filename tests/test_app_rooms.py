"""HTTP-level tests for /start, /join, and the /t/{code} table shell."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from _db_support import make_test_engine
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from sandbox.web.app import app, get_session
from sandbox.web.identity import COOKIE_NAME


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient backed by a fresh, isolated in-memory database."""
    engine = make_test_engine()
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_session() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app, follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_start_form_renders(client: TestClient) -> None:
    response = client.get("/start")

    assert response.status_code == 200
    assert "Value Cards Trading" in response.text


def test_starting_a_room_redirects_to_the_table_and_sets_a_cookie(
    client: TestClient,
) -> None:
    response = client.post(
        "/start",
        data={
            "game_slug": "value-cards-trading",
            "display_name": "Ada",
            "as_facilitator": "true",
        },
    )

    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/t/")
    assert COOKIE_NAME in response.cookies


def test_starting_a_room_without_a_name_shows_an_error(client: TestClient) -> None:
    response = client.post(
        "/start", data={"game_slug": "value-cards-trading", "display_name": "  "}
    )

    assert response.status_code == 400
    assert "Enter a name" in response.text


def test_the_facilitator_can_open_their_own_table(client: TestClient) -> None:
    start = client.post(
        "/start",
        data={
            "game_slug": "value-cards-trading",
            "display_name": "Ada",
            "as_facilitator": "true",
        },
    )
    code = start.headers["location"].removeprefix("/t/")

    table_page = client.get(f"/t/{code}")

    assert table_page.status_code == 200
    assert code in table_page.text
    assert "Ada" in table_page.text


def test_visiting_a_table_before_joining_redirects_to_join(client: TestClient) -> None:
    start = client.post(
        "/start",
        data={
            "game_slug": "value-cards-trading",
            "display_name": "Ada",
            "as_facilitator": "true",
        },
    )
    code = start.headers["location"].removeprefix("/t/")

    # A fresh client carries no cookie, but shares the same overridden,
    # already-seeded database as ``client`` (the override lives on ``app``).
    other_client = TestClient(app, follow_redirects=False)
    response = other_client.get(f"/t/{code}")

    assert response.status_code == 307
    assert response.headers["location"] == f"/join?code={code}"


def test_visiting_an_unknown_table_404s(client: TestClient) -> None:
    response = client.get("/t/ZZZZZZ")

    assert response.status_code == 404


def test_joining_a_room_seats_the_participant_and_redirects(
    client: TestClient,
) -> None:
    start = client.post(
        "/start",
        data={
            "game_slug": "value-cards-trading",
            "display_name": "Ada",
            "as_facilitator": "true",
        },
    )
    code = start.headers["location"].removeprefix("/t/")

    joiner = TestClient(app, follow_redirects=False)
    join_response = joiner.post(
        "/join", data={"room_code": code, "display_name": "Grace"}
    )

    assert join_response.status_code == 303
    assert join_response.headers["location"] == f"/t/{code}"

    table_page = joiner.get(f"/t/{code}")
    assert "Grace" in table_page.text


def test_joining_an_unknown_code_shows_an_error(client: TestClient) -> None:
    response = client.post(
        "/join", data={"room_code": "ZZZZZZ", "display_name": "Grace"}
    )

    assert response.status_code == 400
    assert "no room" in response.text
