"""The record: export, anonymising, retention, deletion, and the consent notice."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from _db_support import make_test_engine
from _room_support import start_room
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from sandbox.db.models import Event, Participant, Reflection, Room
from sandbox.model import SetText
from sandbox.web.app import app, get_session
from sandbox.web.record import (
    build_record,
    data_dictionary_markdown,
    pseudonym,
    record_zip,
)
from sandbox.web.rooms import (
    append_event,
    delete_room_record,
    is_dormant,
    purge_date,
    purge_expired,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = make_test_engine()
    made = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override() -> Iterator[Session]:
        session = made()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_session] = override
    try:
        yield made
    finally:
        app.dependency_overrides.pop(get_session, None)


def _client(factory: sessionmaker[Session]) -> TestClient:
    return TestClient(app, follow_redirects=False)


def _room_with_people(
    client: TestClient, factory: sessionmaker[Session]
) -> tuple[str, TestClient]:
    """A room whose facilitator is Ada, with Grace joined, and a typed note."""
    response = start_room(
        client, data={"display_name": "Ada Lovelace", "as_facilitator": "true"}
    )
    code = response.headers["location"].rsplit("/", 1)[1]
    other = TestClient(app, follow_redirects=False)
    other.post("/join", data={"room_code": code, "display_name": "Grace Hopper"})
    with factory() as session:
        room = session.query(Room).filter_by(code=code).one()
        grace = session.query(Participant).filter_by(display_name="Grace Hopper").one()
        append_event(
            session,
            room,
            actor_seat=grace.seat_id,
            op=SetText(piece_id="note-1", text="My secret reasoning"),
        )
        session.add(
            Reflection(
                room_id=room.id,
                participant_id=grace.id,
                prompt_key="p1",
                body="private thought",
                visibility="private",
            )
        )
        session.add(
            Reflection(
                room_id=room.id,
                participant_id=grace.id,
                prompt_key="p2",
                body="shared thought",
                visibility="shared",
            )
        )
        session.commit()
    return code, other


def test_pseudonyms_run_past_z() -> None:
    assert [pseudonym(0), pseudonym(1), pseudonym(25), pseudonym(26)] == [
        "Participant A",
        "Participant B",
        "Participant Z",
        "Participant AA",
    ]


def test_anonymised_export_has_no_display_name(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, _ = _room_with_people(client, factory)

    for url in (f"/t/{code}/record.json", f"/t/{code}/record.zip"):
        text = client.get(url, params={"anonymise": "true", "include_text": "true"})
        if url.endswith(".zip"):
            archive = zipfile.ZipFile(io.BytesIO(text.content))
            body = "".join(archive.read(name).decode() for name in archive.namelist())
        else:
            body = text.text
        assert "Ada" not in body
        assert "Grace" not in body
        assert "Lovelace" not in body
        assert code not in body


def test_written_text_is_left_out_unless_asked_for(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, _ = _room_with_people(client, factory)

    without = client.get(f"/t/{code}/record.json").text
    with_text = client.get(f"/t/{code}/record.json", params={"include_text": "true"})

    assert "My secret reasoning" not in without
    assert "shared thought" not in without
    assert "My secret reasoning" in with_text.text
    assert "shared thought" in with_text.text
    # What a person kept private is never exported, even with text on.
    assert "private thought" not in with_text.text


def test_export_names_its_schema_and_lists_every_event(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, _ = _room_with_people(client, factory)

    data = client.get(f"/t/{code}/record.json").json()

    assert data["schema_version"] == 1
    seqs = [event["seq"] for event in data["events"]]
    assert seqs == sorted(seqs)
    assert "SetText" in {event["op_type"] for event in data["events"]}
    assert {p["display_name"] for p in data["participants"]} >= {"Ada Lovelace"}


def test_csv_export_has_one_file_per_event_type(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, _ = _room_with_people(client, factory)

    response = client.get(f"/t/{code}/record.zip")

    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert "manifest.json" in names
    assert "events/SetText.csv" in names
    assert "events/AddSeat.csv" in names  # a transaction's steps get their own file


def test_only_the_facilitator_can_export_or_delete(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, grace = _room_with_people(client, factory)

    assert grace.get(f"/t/{code}/record.json").status_code == 403
    assert grace.get(f"/t/{code}/record.zip").status_code == 403
    assert grace.post(f"/t/{code}/record/delete").status_code == 403
    assert TestClient(app).get(f"/t/{code}/record.json").status_code == 403
    with factory() as session:
        assert session.query(Room).count() == 1


def test_the_facilitator_can_delete_the_whole_record(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, _ = _room_with_people(client, factory)

    response = client.post(f"/t/{code}/record/delete")

    assert response.status_code == 303
    with factory() as session:
        assert session.query(Room).count() == 0
        assert session.query(Participant).count() == 0
        assert session.query(Event).count() == 0
        assert session.query(Reflection).count() == 0


def test_the_facilitator_sees_retention_and_others_do_not(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, grace = _room_with_people(client, factory)

    assert "12 hours" in client.get(f"/t/{code}").text
    assert "The record of this room" not in grace.get(f"/t/{code}").text


def test_rooms_go_dormant_after_twelve_hours_and_are_purged_after_thirty_days(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, _ = _room_with_people(client, factory)
    with factory() as session:
        room = session.query(Room).filter_by(code=code).one()
        room.last_active_at = NOW
        assert not is_dormant(room, NOW + timedelta(hours=11))
        assert is_dormant(room, NOW + timedelta(hours=12))
        assert purge_date(room) == NOW + timedelta(days=30)

        assert purge_expired(session, NOW + timedelta(days=29)) == []
        assert purge_expired(session, NOW + timedelta(days=30)) == [code]
        assert session.query(Room).count() == 0
        assert session.query(Event).count() == 0


def test_delete_room_record_removes_everything(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, _ = _room_with_people(client, factory)
    with factory() as session:
        room = session.query(Room).filter_by(code=code).one()
        delete_room_record(session, room)
        assert session.query(Room).count() == 0


def test_the_join_screen_has_no_consent_notice() -> None:
    page = TestClient(app).get("/join").text

    assert "consent" not in page.lower()
    assert not (ROOT / "CONSENT.md").exists()


def test_the_facilitator_exports_with_checkboxes(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, _ = _room_with_people(client, factory)

    page = client.get(f"/t/{code}").text

    assert 'name="include_text"' in page
    assert 'name="anonymise"' in page
    assert f'formaction="/t/{code}/record.zip"' in page


def test_each_exercise_shows_its_learning_outcomes() -> None:
    app_client = TestClient(app)

    democracy = app_client.get("/exercises/democracy-simulation").text
    cards = app_client.get("/exercises/value-cards-trading").text

    for title in (
        "Experience a deliberative process",
        "Practice civil discourse skills",
        "Face trade-offs between moral values and strategic goals",
    ):
        assert title in democracy
    assert "Learning outcomes" in cards
    assert "Self-knowledge" in cards
    assert "Engagement across differences" in cards


def test_each_room_offers_its_own_activities_and_its_own_debrief() -> None:
    from sandbox.games import GAMES
    from sandbox.web.live import activity_choices

    offered = {
        kind: [choice.slug for choice in activity_choices(GAMES[kind])]
        for kind in ("value-cards-room", "democracy-room")
    }

    assert offered == {
        "value-cards-room": ["value-cards-trading", "value-cards-debrief"],
        "democracy-room": ["scenario-1", "scenario-2", "democracy-debrief"],
    }
    scenario_2 = activity_choices(GAMES["democracy-room"])[1]
    assert scenario_2.class_only
    assert [option.id for option in scenario_2.options] == ["city"]


def test_the_help_page_explains_records_and_the_landing_page_links_to_it() -> None:
    client = TestClient(app)

    assert 'href="/help"' in client.get("/").text
    page = client.get("/help").text
    for phrase in (
        "never records audio or video",
        "12 hours",
        "30 days",
        "JSON",
        "tperry@fas.harvard.edu",
    ):
        assert phrase in page


def test_the_data_dictionary_is_current_and_covers_every_logged_type() -> None:
    written = (ROOT / "docs" / "DATA-DICTIONARY.md").read_text()

    assert written == data_dictionary_markdown()
    for name in ("MoveToZone", "OfferSwap", "SetClassDecision", "Transaction"):
        assert f"### {name}" in written


def test_build_record_is_stable_within_an_export(
    factory: sessionmaker[Session],
) -> None:
    client = _client(factory)
    code, _ = _room_with_people(client, factory)
    with factory() as session:
        room = session.query(Room).filter_by(code=code).one()
        first = build_record(session, room, anonymise=True, exported_at=NOW)
        again = build_record(session, room, anonymise=True, exported_at=NOW)
        assert json.dumps(first) == json.dumps(again)
        assert record_zip(first)
