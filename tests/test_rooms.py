"""The room service layer: creation, joining, seating, and the write path."""

from __future__ import annotations

import pytest
from _db_support import db_session

from sandbox.db.models import Event
from sandbox.model import (
    Grab,
    Move,
    Ok,
    Piece,
    PieceKind,
    Reject,
    Rotate,
    facilitator_seat,
)
from sandbox.web import rooms


def _lone_card() -> Piece:
    return Piece(
        id="card-1",
        kind=PieceKind.CARD,
        component_id="the-1-of-values",
        zone_id="table",
        x=0.0,
        y=0.0,
        z=0,
    )


def test_generate_room_code_is_the_right_shape_and_alphabet() -> None:
    with db_session() as session:
        code = rooms.generate_room_code(session)

    assert len(code) == rooms.CODE_LENGTH
    assert set(code) <= set(rooms.CODE_ALPHABET)


def test_create_room_rejects_an_unknown_exercise() -> None:
    with db_session() as session, pytest.raises(rooms.UnknownExerciseError):
        rooms.create_room(
            session,
            game_slug="not-a-real-exercise",
            facilitator_cookie_id="cookie-1",
            facilitator_name="Ada",
            as_facilitator=True,
        )


def test_a_new_room_has_no_facilitator_unless_its_creator_chooses_to_be() -> None:
    with db_session() as session:
        room, creator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="cookie-1",
            facilitator_name="Ada",
        )
        session.commit()
        table = rooms.load_table(session, room)
        assert creator.seat_id is not None
        assert table.seats[creator.seat_id].is_facilitator is False
        assert facilitator_seat(table) is None


def test_someone_may_join_as_the_facilitator_but_only_one_at_a_time() -> None:
    with db_session() as session:
        room, _creator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="cookie-1",
            facilitator_name="Ada",
        )
        session.commit()
        chosen = rooms.join_room(
            session,
            code=room.code,
            cookie_id="cookie-2",
            display_name="Ben",
            as_facilitator=True,
        )
        session.commit()
        table = rooms.load_table(session, room)
        assert chosen.seat_id is not None
        assert facilitator_seat(table) == chosen.seat_id
        with pytest.raises(rooms.FacilitatorTakenError):
            rooms.join_room(
                session,
                code=room.code,
                cookie_id="cookie-3",
                display_name="Cy",
                as_facilitator=True,
            )


def test_create_room_seats_its_facilitator() -> None:
    with db_session() as session:
        room, facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="cookie-1",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        session.commit()

        assert room.status == "open"
        assert facilitator.seat_id is not None
        assert facilitator.is_observer is False

        table = rooms.load_table(session, room)
        seat = table.seats[facilitator.seat_id]
        assert seat.is_facilitator is True
        assert seat.participant_id == facilitator.id


def test_join_room_seats_a_new_participant_and_reattaches_a_returning_one() -> None:
    with db_session() as session:
        room, _facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        session.commit()

        participant = rooms.join_room(
            session, code=room.code, cookie_id="cookie-2", display_name="Grace"
        )
        session.commit()
        assert participant.seat_id is not None
        assert participant.is_observer is False

        # The same browser rejoining reclaims the same row and seat.
        again = rooms.join_room(
            session, code=room.code.lower(), cookie_id="cookie-2", display_name="Grace"
        )
        assert again.id == participant.id
        assert again.seat_id == participant.seat_id


def test_join_room_dedupes_display_names() -> None:
    with db_session() as session:
        room, _facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        session.commit()

        first = rooms.join_room(
            session, code=room.code, cookie_id="cookie-a", display_name="Sam"
        )
        second = rooms.join_room(
            session, code=room.code, cookie_id="cookie-b", display_name="Sam"
        )

        assert first.display_name == "Sam"
        assert second.display_name == "Sam (2)"


def test_join_room_seats_up_to_the_cap_then_makes_observers() -> None:
    with db_session() as session:
        room, _facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
            config={"max_seats": 2},
        )
        session.commit()

        second = rooms.join_room(
            session, code=room.code, cookie_id="cookie-2", display_name="Grace"
        )
        third = rooms.join_room(
            session, code=room.code, cookie_id="cookie-3", display_name="Alan"
        )

        assert second.seat_id is not None
        assert third.seat_id is None
        assert third.is_observer is True


def test_join_room_raises_for_an_unknown_code() -> None:
    with db_session() as session, pytest.raises(rooms.RoomNotFoundError):
        rooms.join_room(
            session, code="ZZZZZZ", cookie_id="cookie-1", display_name="Ada"
        )


def test_join_room_raises_for_a_closed_room() -> None:
    with db_session() as session:
        room, _facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        rooms.close_room(session, room)
        session.commit()

        with pytest.raises(rooms.RoomClosedError):
            rooms.join_room(
                session, code=room.code, cookie_id="cookie-2", display_name="Grace"
            )


def test_claim_seat_moves_a_participant_and_frees_their_old_seat() -> None:
    with db_session() as session:
        room, _facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
            config={"max_seats": 3},
        )
        participant = rooms.join_room(
            session, code=room.code, cookie_id="cookie-2", display_name="Grace"
        )
        third = rooms.join_room(
            session, code=room.code, cookie_id="cookie-3", display_name="Alan"
        )
        session.commit()
        old_seat_id = participant.seat_id
        empty_seat_id = third.seat_id
        assert old_seat_id is not None
        assert empty_seat_id is not None
        rooms.release_seat(session, room, third)
        session.commit()

        rooms.claim_seat(session, room, participant, empty_seat_id)

        assert participant.seat_id == empty_seat_id
        table_after = rooms.load_table(session, room)
        assert table_after.seats[old_seat_id].participant_id is None
        assert table_after.seats[empty_seat_id].participant_id == participant.id


def test_claim_seat_rejects_an_already_taken_seat() -> None:
    with db_session() as session:
        room, facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        participant = rooms.join_room(
            session, code=room.code, cookie_id="cookie-2", display_name="Grace"
        )
        session.commit()

        with pytest.raises(rooms.SeatUnavailableError):
            rooms.claim_seat(session, room, participant, facilitator.seat_id or "")


def test_make_observer_then_release_frees_and_marks_the_participant() -> None:
    with db_session() as session:
        room, _facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        participant = rooms.join_room(
            session, code=room.code, cookie_id="cookie-2", display_name="Grace"
        )
        session.commit()
        seat_id = participant.seat_id
        assert seat_id is not None

        rooms.make_observer(session, room, participant)

        assert participant.seat_id is None
        assert participant.is_observer is True
        table = rooms.load_table(session, room)
        assert table.seats[seat_id].participant_id is None


def test_rename_dedupes_against_the_room() -> None:
    with db_session() as session:
        room, facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        participant = rooms.join_room(
            session, code=room.code, cookie_id="cookie-2", display_name="Grace"
        )
        session.commit()

        rooms.rename(session, room, participant, "Ada")

        assert participant.display_name == "Ada (2)"
        assert facilitator.display_name == "Ada"


def test_remove_participant_frees_their_seat_and_deletes_the_row() -> None:
    with db_session() as session:
        room, _facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        participant = rooms.join_room(
            session, code=room.code, cookie_id="cookie-2", display_name="Grace"
        )
        session.commit()
        seat_id = participant.seat_id
        assert seat_id is not None

        rooms.remove_participant(session, room, participant)
        session.commit()

        table = rooms.load_table(session, room)
        assert table.seats[seat_id].participant_id is None
        assert rooms.get_participant(session, room.id, "cookie-2") is None


def test_pause_and_resume_room() -> None:
    with db_session() as session:
        room, _facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )

        rooms.pause_room(session, room)
        assert room.status == "paused"

        rooms.resume_room(session, room)
        assert room.status == "open"


def test_apply_op_persists_state_logs_an_event_and_is_idempotent() -> None:
    with db_session() as session:
        room, facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        session.commit()
        seat_id = facilitator.seat_id
        assert seat_id is not None

        table = rooms.load_table(session, room)
        table.pieces["card-1"] = _lone_card()
        rooms.save_table_state(session, room, table)
        session.commit()

        move = Move(piece_id="card-1", x=99.0, y=5.0)
        applied = rooms.apply_op(session, room, seat_id, move)
        session.commit()

        assert isinstance(applied.outcome, Ok)
        # Event 1 is the transaction that built the room's table.
        assert applied.seq == 2

        reloaded = rooms.load_table(session, room)
        assert reloaded.pieces["card-1"].x == 99.0

        events = session.query(Event).filter_by(room_id=room.id).all()
        assert [event.op_type for event in events] == ["Transaction", "Move"]
        assert events[1].payload["x"] == 99.0

        # Retrying the same op_id is a no-op: no new event, same outcome.
        replay = rooms.apply_op(session, room, seat_id, move)
        session.commit()
        assert isinstance(replay.outcome, Ok)
        events_after_replay = session.query(Event).filter_by(room_id=room.id).all()
        assert len(events_after_replay) == 2


def test_apply_op_rejects_without_writing_anything() -> None:
    with db_session() as session:
        room, facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        session.commit()

        rotate = Rotate(piece_id="does-not-exist")
        applied = rooms.apply_op(session, room, facilitator.seat_id or "", rotate)

        assert isinstance(applied.outcome, Reject)
        assert applied.seq is None


def test_apply_op_refuses_activity_on_a_closed_room() -> None:
    with db_session() as session:
        room, facilitator = rooms.create_room(
            session,
            game_slug="value-cards-trading",
            facilitator_cookie_id="facilitator-cookie",
            facilitator_name="Ada",
            as_facilitator=True,
        )
        rooms.close_room(session, room)
        session.commit()

        applied = rooms.apply_op(
            session, room, facilitator.seat_id or "", Grab(piece_id="anything")
        )

        assert isinstance(applied.outcome, Reject)


def test_a_room_seats_thirty_and_the_next_person_observes() -> None:
    with db_session() as session:
        room, _creator = rooms.create_room(
            session,
            game_slug="value-cards-room",
            facilitator_cookie_id="cookie-0",
            facilitator_name="Ada",
        )
        session.commit()
        joined = [
            rooms.join_room(
                session,
                code=room.code,
                cookie_id=f"cookie-{number}",
                display_name=f"Person {number}",
            )
            for number in range(1, 30)
        ]
        session.commit()
        assert all(person.seat_id is not None for person in joined)
        assert len(rooms.load_table(session, room).seats) == 30
        extra = rooms.join_room(
            session, code=room.code, cookie_id="cookie-30", display_name="Extra"
        )
        assert extra.seat_id is None and extra.is_observer
