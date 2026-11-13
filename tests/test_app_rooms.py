"""HTTP-level tests for opening a room, /join, and the /t/{code} table shell."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from _db_support import make_test_engine
from _room_support import start_room
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


def test_opening_a_room_sends_its_opener_to_the_join_form(client: TestClient) -> None:
    response = client.post("/rooms", data={"kind": "value-cards-room"})

    assert response.status_code == 303
    assert response.headers["location"].startswith("/join?code=")
    form = client.get(response.headers["location"]).text
    code = response.headers["location"].removeprefix("/join?code=")
    assert f'value="{code}"' in form


def test_each_exercise_page_opens_its_own_kind_of_room(client: TestClient) -> None:
    for slug, kind in (
        ("value-cards-trading", "value-cards-room"),
        ("democracy-simulation", "democracy-room"),
    ):
        page = client.get(f"/exercises/{slug}").text
        assert f'name="kind" value="{kind}"' in page


def test_a_new_room_has_no_facilitator(
    client: TestClient,
) -> None:
    response = start_room(client, data={"display_name": "Ada"})

    assert response.status_code == 303
    page = client.get(response.headers["location"]).text
    assert "Facilitator</span>" not in page


def test_starting_a_room_redirects_to_the_table_and_sets_a_cookie(
    client: TestClient,
) -> None:
    response = start_room(
        client,
        data={
            "display_name": "Ada",
            "as_facilitator": "true",
        },
    )

    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/t/")
    assert COOKIE_NAME in response.cookies


def test_starting_a_room_without_a_name_shows_an_error(client: TestClient) -> None:
    response = start_room(client, data={"display_name": "  "})

    assert response.status_code == 400
    assert "Enter a name" in response.text


def test_the_facilitator_can_open_their_own_table(client: TestClient) -> None:
    start = start_room(
        client,
        data={
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
    start = start_room(
        client,
        data={
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
    start = start_room(
        client,
        data={
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


def test_a_closed_room_says_it_is_closed_and_what_to_do(client: TestClient) -> None:
    from sandbox.web.rooms import close_room, get_room_by_code

    response = start_room(client, data={"display_name": "Ada"})
    code = response.headers["location"].removeprefix("/t/")
    session_gen = app.dependency_overrides[get_session]()
    session = next(session_gen)
    room = get_room_by_code(session, code)
    assert room is not None
    close_room(session, room)
    with pytest.raises(StopIteration):
        next(session_gen)

    page = client.get(f"/t/{code}", headers={"accept": "text/html"})
    assert page.status_code == 410
    assert "This room is closed" in page.text
    assert "ask for a new room code" in page.text

    joined = client.post("/join", data={"room_code": code, "display_name": "Bo"})
    assert "closed" in joined.text
    assert "Ask the facilitator for a new room code" in joined.text


def test_an_unknown_code_on_the_join_form_says_what_to_do(client: TestClient) -> None:
    response = client.post("/join", data={"room_code": "ZZZZZZ", "display_name": "Bo"})
    assert "Check the code for typing mistakes" in response.text


def test_the_join_form_links_back_to_the_exercise_it_came_from(
    client: TestClient,
) -> None:
    page = client.get("/exercises/value-cards-trading").text
    assert 'href="/join?exercise=value-cards-trading"' in page

    form = client.get("/join?exercise=value-cards-trading").text
    assert 'href="/exercises/value-cards-trading"' in form
    assert 'name="exercise" value="value-cards-trading"' in form

    refused = client.post(
        "/join",
        data={
            "room_code": "ZZZZZZ",
            "display_name": "Bo",
            "exercise": "value-cards-trading",
        },
    )
    assert 'href="/exercises/value-cards-trading"' in refused.text


def test_the_join_form_for_a_new_room_links_back_to_its_exercise(
    client: TestClient,
) -> None:
    for kind, slug in (
        ("value-cards-room", "value-cards-trading"),
        ("democracy-room", "democracy-simulation"),
    ):
        opened = client.post("/rooms", data={"kind": kind})
        form = client.get(opened.headers["location"]).text
        assert f'href="/exercises/{slug}"' in form


def test_the_join_form_with_no_exercise_links_only_to_the_landing_page(
    client: TestClient,
) -> None:
    for url in ("/join", "/join?exercise=no-such-thing", "/join?code=ZZZZZZ"):
        form = client.get(url).text
        assert 'href="/exercises/' not in form
        assert '<a href="/">← Ethics Sandbox</a>' in form
