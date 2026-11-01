"""Debriefs, replay, notes and reflections, against recorded sessions.

Each test plays a real session of an exercise through the room service (so
every operation is logged exactly as in production), then reads it back
through the pages a facilitator and a participant would open.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from _db_support import make_test_engine
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from sandbox.db.models import Participant, Room
from sandbox.db.snapshot import to_snapshot
from sandbox.games import GAMES
from sandbox.games.engine import build_activity_start, build_macro
from sandbox.model import (
    AcceptSwap,
    DeclineSwap,
    MoveToZone,
    OfferSwap,
    Ok,
    OpenActivity,
    Operation,
    Reject,
    SetActivityPlayers,
    SetText,
    ShowTo,
    Transaction,
)
from sandbox.web import rooms
from sandbox.web.app import app, get_session
from sandbox.web.replay import load_events, replay, seed_of


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


class Played:
    """A room played through the room service, and a browser for each person."""

    def __init__(self, factory: sessionmaker[Session], names: list[str]) -> None:
        self.factory = factory
        self.clients: dict[str, TestClient] = {}
        first = TestClient(app, follow_redirects=False)
        response = first.post(
            "/start", data={"display_name": names[0], "as_facilitator": "true"}
        )
        self.code = response.headers["location"].rsplit("/", 1)[1]
        self.clients[names[0]] = first
        for name in names[1:]:
            other = TestClient(app, follow_redirects=False)
            other.post("/join", data={"room_code": self.code, "display_name": name})
            self.clients[name] = other

    def seat(self, name: str) -> str:
        with self.factory() as session:
            person = session.query(Participant).filter_by(display_name=name).one()
            assert person.seat_id is not None
            return person.seat_id

    def table(self) -> Any:
        with self.factory() as session:
            room = session.query(Room).filter_by(code=self.code).one()
            return rooms.load_table(session, room)

    def do(self, seat: str, op: Operation) -> None:
        with self.factory() as session:
            room = session.query(Room).filter_by(code=self.code).one()
            result = rooms.apply_op(session, room, seat, op)
            assert isinstance(result.outcome, Ok), result.outcome
            session.commit()

    def press(self, slug: str, macro: str, aid: str, seat: str = "seat-1") -> None:
        built = build_macro(GAMES[slug], self.table(), seat, macro, aid)
        assert not isinstance(built, Reject), built
        self.do(seat, built)

    def start(self, slug: str, seat: str, players: list[str], **options: str) -> str:
        meta = GAMES[slug].definition.meta
        self.do(
            seat,
            OpenActivity(
                kind=slug,
                title=meta.title,
                min_players=meta.players.min,
                max_players=meta.players.max,
                options=tuple(options.items()),
            ),
        )
        aid = next(reversed(self.table().activities))
        if len(players) != len(set(players)):
            raise AssertionError("players must be distinct")
        self.do("seat-1", SetActivityPlayers(aid, tuple(players)))
        built = build_activity_start(GAMES[slug], self.table(), "seat-1", aid)
        assert isinstance(built, Transaction), built
        self.do("seat-1", built)
        return str(aid)

    def get(self, name: str, url: str) -> Any:
        return self.clients[name].get(url)


# -- Value Cards Trading ------------------------------------------------------------


def _value_cards(factory: sessionmaker[Session]) -> tuple[Played, str]:
    played = Played(factory, ["Ada", "Bea", "Cy", "Di"])
    aid = played.start("value-cards-trading", "seat-1", ["seat-2", "seat-3", "seat-4"])
    played.press("value-cards-trading", "deal", aid)
    table = played.table()
    give = table.pieces_in_zone(f"{aid}:hand-seat-2")[0].id
    want = table.pieces_in_zone(f"{aid}:hand-seat-3")[0].id
    offer = OfferSwap(to_seat="seat-3", give=(give,), want=(want,))
    played.do("seat-2", offer)
    played.do("seat-3", AcceptSwap(offer_id=offer.op_id))
    table = played.table()
    refused = OfferSwap(
        to_seat="seat-2",
        give=(table.pieces_in_zone(f"{aid}:hand-seat-4")[0].id,),
        want=(table.pieces_in_zone(f"{aid}:hand-seat-2")[0].id,),
    )
    played.do("seat-4", refused)
    played.do("seat-2", DeclineSwap(offer_id=refused.op_id))
    table = played.table()
    for seat in ("seat-2", "seat-3"):
        card = table.pieces_in_zone(f"{aid}:hand-{seat}")[1].id
        played.do(seat, MoveToZone(piece_id=card, zone_id=f"{aid}:top-three-{seat}"))
    shown = played.table().pieces_in_zone(f"{aid}:top-three-seat-3")[0].id
    played.do("seat-3", ShowTo(piece_id=shown, seat_ids=("seat-2", "seat-4")))
    return played, aid


def test_replay_rebuilds_the_table_the_room_ended_with(
    factory: sessionmaker[Session],
) -> None:
    played, _ = _value_cards(factory)

    with factory() as session:
        room = session.query(Room).filter_by(code=played.code).one()
        rebuilt = replay(load_events(session, room), seed_of(session, room))
        live = rooms.load_table(session, room)

    assert rebuilt.skipped == 0
    assert to_snapshot(rebuilt.table) == to_snapshot(live)


def test_the_value_cards_debrief_has_every_section(
    factory: sessionmaker[Session],
) -> None:
    played, aid = _value_cards(factory)

    page = played.get("Ada", f"/t/{played.code}/debrief/{aid}").text

    for heading in (
        "Hands, side by side",
        "Top three",
        "The trades, in order",
        "Across the trio",
        "Timing",
        "Questions for discussion",
    ):
        assert heading in page
    assert "Bea gave" in page and "Cy gave" in page
    assert "Offers that were declined" in page
    assert "Cards that changed hands" in page
    assert "Cards that never moved" in page
    assert "Cards nobody put in a top three" in page
    assert "Self-knowledge" in page and "Engagement across differences" in page


def test_an_unshown_top_three_is_visible_only_to_its_owner(
    factory: sessionmaker[Session],
) -> None:
    played, aid = _value_cards(factory)
    url = f"/t/{played.code}/debrief/{aid}"
    played.get("Ada", url)  # the facilitator can always read it
    with factory() as session:
        room = session.query(Room).filter_by(code=played.code).one()
        from sandbox.web.debrief import save_settings

        save_settings(room, aid, {"open": True})
        session.commit()

    def top_row(name: str, who: str) -> str:
        page = str(played.get(name, url).text)
        start = page.index(f"<td>{who}</td>", page.index("Top three"))
        return page[start : start + 400]

    # Cy showed their top three: everyone reads it.
    assert "not shown" not in top_row("Di", "Cy").split("</tr>")[0]
    # Bea did not: Di, who is not Bea, reads "not shown"; Bea reads their own.
    assert "not shown" in top_row("Di", "Bea").split("</tr>")[0]
    assert "not shown" not in top_row("Bea", "Bea").split("</tr>")[0]
    # The facilitator is not the owner either.
    assert "not shown" in top_row("Ada", "Bea").split("</tr>")[0]


def test_a_debrief_is_closed_to_participants_until_the_facilitator_opens_it(
    factory: sessionmaker[Session],
) -> None:
    played, aid = _value_cards(factory)
    url = f"/t/{played.code}/debrief/{aid}"

    assert played.get("Bea", url).status_code == 403
    response = played.clients["Ada"].post(
        f"/t/{played.code}/debrief/{aid}/open",
        data={"opened": "true", "is_class": "false"},
    )
    assert response.status_code == 303
    assert played.get("Bea", url).status_code == 200
    assert "Value Cards Trading" in played.get("Bea", f"/t/{played.code}/debrief").text


def test_only_the_facilitator_adds_notes_and_they_are_kept_in_the_log(
    factory: sessionmaker[Session],
) -> None:
    played, aid = _value_cards(factory)
    base = f"/t/{played.code}/debrief/{aid}"

    refused = played.clients["Bea"].post(
        f"{base}/note", data={"text": "sneaky", "outcome": ""}
    )
    kept = played.clients["Ada"].post(
        f"{base}/note",
        data={
            "text": "Cy asked what Bea meant by dignity",
            "outcome": "Self-knowledge",
        },
    )

    assert refused.status_code == 403
    assert kept.status_code == 303
    page = played.get("Ada", base).text
    assert "Cy asked what Bea meant by dignity" in page
    assert "Self-knowledge" in page
    with factory() as session:
        room = session.query(Room).filter_by(code=played.code).one()
        events = load_events(session, room)
    assert events[-1].op_type == "Record"
    assert events[-1].payload["label"] == "observation"
    # Notes are for the facilitator only, even once the debrief is open.
    played.clients["Ada"].post(
        f"{base}/open", data={"opened": "true", "is_class": "false"}
    )
    assert "Cy asked what Bea meant" not in played.get("Bea", base).text
    # And they are written text: left out of an export unless asked for.
    export = played.get("Ada", f"/t/{played.code}/record.json").text
    assert "Cy asked what Bea meant" not in export
    with_text = played.get(
        "Ada", f"/t/{played.code}/record.json?include_text=true"
    ).text
    assert "Cy asked what Bea meant" in with_text


# -- reflection ----------------------------------------------------------------------


def test_a_reflection_is_private_unless_shared(
    factory: sessionmaker[Session],
) -> None:
    played, aid = _value_cards(factory)
    prompt = f"{aid}/debrief-01"
    played.clients["Bea"].post(
        f"/t/{played.code}/reflect",
        data={"scope_prompt": prompt, "body": "kept to myself"},
    )
    played.clients["Cy"].post(
        f"/t/{played.code}/reflect",
        data={"scope_prompt": prompt, "body": "for everyone", "share": "true"},
    )
    played.clients["Ada"].post(
        f"/t/{played.code}/debrief/{aid}/open",
        data={"opened": "true", "is_class": "false"},
    )

    page = played.get("Di", f"/t/{played.code}/debrief/{aid}").text
    facilitator = played.get("Ada", f"/t/{played.code}/debrief/{aid}").text

    assert "for everyone" in page
    assert "kept to myself" not in page
    assert "kept to myself" not in facilitator
    assert "kept to myself" in played.get("Bea", f"/t/{played.code}/reflect").text
    assert "kept to myself" not in played.get("Cy", f"/t/{played.code}/reflect").text


# -- the class debrief and the replay page -------------------------------------------


def test_the_class_debrief_pools_the_trios(factory: sessionmaker[Session]) -> None:
    played, aid = _value_cards(factory)
    played.do("seat-1", _end_activity(aid))

    page = played.get("Ada", f"/t/{played.code}/debrief/{aid}").text

    # An ended activity can still be read, from the table as it stood.
    assert "The trades, in order" in page


def _end_activity(aid: str) -> Operation:
    from sandbox.model import EndActivity

    return EndActivity(activity_id=aid)


def test_replay_is_for_the_facilitator_and_shows_public_or_every_face(
    factory: sessionmaker[Session],
) -> None:
    played, aid = _value_cards(factory)
    base = f"/t/{played.code}/replay"

    assert played.get("Bea", base).status_code == 403
    assert played.get("Ada", base).status_code == 200
    with factory() as session:
        room = session.query(Room).filter_by(code=played.code).one()
        last = load_events(session, room)[-1].seq
    public = played.get("Ada", f"{base}/frame?seq={last}").text
    everything = played.get("Ada", f"{base}/frame?seq={last}&faces=true").text
    assert played.get("Bea", f"{base}/frame?seq={last}").status_code == 403

    assert "table-picture" in public
    # Hands are public in this exercise; the deck is hidden, so every-face
    # mode draws strictly more card titles than the public view.
    assert everything.count("<text") >= public.count("<text")
    assert "Every face is showing." in everything


# -- Democracy Simulation ------------------------------------------------------------

PEOPLE = [
    "Ada",
    "Bea",
    "Cy",
    "Di",
    "Eli",
    "Fay",
    "Gus",
    "Hal",
    "Ivy",
    "Jo",
    "Kit",
    "Lea",
]


def _democracy(
    factory: sessionmaker[Session], city: str, people: int
) -> tuple[Played, str, list[str]]:
    slug = "democracy-simulation"
    played = Played(factory, PEOPLE[:people])
    seats = tuple(f"seat-{n}" for n in range(1, people + 1))
    aid = played.start(slug, "seat-1", list(seats), city=city, phase="1")
    played.press(slug, "deal", aid)
    if city == "potamosia":
        played.press(slug, "choose_moderators", aid)
    played.press(slug, "start_meeting", aid)
    played.press(slug, "new_proposal", aid, "seat-2")
    table = played.table()
    note = table.pieces_in_zone(f"{aid}:proposals")[-1]
    played.do("seat-2", SetText(piece_id=note.id, text="Build the dam"))
    played.do("seat-1", MoveToZone(piece_id=note.id, zone_id=f"{aid}:floor"))
    played.press(slug, "put_to_vote", aid)
    table = played.table()
    cards = GAMES[slug].cards()
    voters = [
        seat for seat in seats if table.pieces_in_zone(f"{aid}:ballot-box-{seat}")
    ]
    if city == "hudrosia":
        voters = [
            seat
            for seat in voters
            if any(
                p.component_id.startswith("role")
                and cards[p.component_id]["council"] == "yes"
                for p in table.pieces_in_zone(f"{aid}:hand-{seat}")
            )
        ]
    for seat in voters[: len(voters) // 2 + 1]:
        box = table.pieces_in_zone(f"{aid}:ballot-box-{seat}")
        token = next(p for p in box if p.component_id == "yes")
        played.do(seat, MoveToZone(piece_id=token.id, zone_id=f"{aid}:ballot-{seat}"))
    played.press(slug, "close_vote", aid)
    return played, aid, voters


def _open(played: Played, key: str) -> None:
    played.clients["Ada"].post(
        f"/t/{played.code}/debrief/{key}/open",
        data={"opened": "true", "is_class": "false"},
    )


def test_a_potamosia_debrief_reads_the_timeline_votes_and_interest(
    factory: sessionmaker[Session],
) -> None:
    played, aid, voters = _democracy(factory, "potamosia", 9)
    _open(played, aid)
    url = f"/t/{played.code}/debrief/{aid}"

    page = played.get("Ada", url).text

    for heading in (
        "Timeline",
        "Votes",
        "Interest against vote",
        "Information that existed in the room",
        "Timing",
        "Questions for discussion",
    ):
        assert heading in page
    assert "Moderators chosen" in page
    assert "Proposal 1 opened" in page and "Proposal 1 written" in page
    assert "Build the dam" in page
    assert "Vote 1 counted" in page
    # Potamosia's hands are public: the vote lists how each person voted.
    assert "<td>For</td></tr>" in page
    # The facilitator sees every row of interest against vote; a participant
    # sees only their own.
    for name in ("Bea", "Cy", "Di"):
        assert f"<td>{name}</td>" in page
    mine = played.get("Cy", url).text
    start = mine.index("Interest against vote")
    end = mine.index("Information that existed")
    section = mine[start:end]
    assert "<td>Cy</td>" in section
    assert "<td>Bea</td>" not in section
    assert "Experience a deliberative process" in page


def test_the_facilitator_ticks_what_surfaced_and_everyone_then_sees_it(
    factory: sessionmaker[Session],
) -> None:
    played, aid, _ = _democracy(factory, "potamosia", 9)
    _open(played, aid)
    url = f"/t/{played.code}/debrief/{aid}"
    page = played.get("Ada", url).text
    assert 'name="surfaced"' in page
    item = page.split('name="surfaced" value="')[1].split('"')[0]

    played.clients["Ada"].post(
        f"{url}/settings",
        data={"which": "surfaced", "surfaced": [item], "is_class": "false"},
    )

    assert (
        played.clients["Bea"]
        .post(f"{url}/settings", data={"which": "surfaced", "surfaced": [item]})
        .status_code
        == 403
    )
    seen = played.get("Bea", url).text
    section = seen[seen.index("Information that existed") :]
    assert "What surfaced" in section
    assert 'name="surfaced"' not in section


def test_hudrosias_council_votes_show_only_the_tally_until_the_facilitator_shows_more(
    factory: sessionmaker[Session],
) -> None:
    played, aid, council = _democracy(factory, "hudrosia", 12)
    _open(played, aid)
    url = f"/t/{played.code}/debrief/{aid}"
    members = [PEOPLE[int(seat.split("-")[1]) - 1] for seat in council]

    def votes(name: str) -> str:
        page = str(played.get(name, url).text)
        return page[page.index("Votes") : page.index("Interest against vote")]

    hidden = votes("Bea")
    assert "For" in hidden and "Present" in hidden
    assert "<td>For</td></tr>" not in hidden  # no per-person vote
    assert "only the tally is shown" in hidden
    played.clients["Ada"].post(
        f"{url}/settings",
        data={"which": "council", "show_council_votes": "true", "is_class": "false"},
    )
    shown = votes("Bea")
    assert any(f"<td>{name}</td>" in shown for name in members)


def test_the_democracy_class_page_sets_democracies_and_oligarchies_apart(
    factory: sessionmaker[Session],
) -> None:
    from sandbox.games.debrief import CLASS_DEBRIEFS, ClassContext
    from sandbox.model import ClassGroup
    from sandbox.web.debrief import RoomLog, Viewer

    slug = "democracy-simulation"
    names = [f"P{n}" for n in range(1, 19)]
    played = Played(factory, names)
    seats = [f"seat-{n}" for n in range(1, 19)]
    aids = [
        played.start(slug, "seat-1", seats[:9], city="potamosia", phase="1"),
        played.start(slug, "seat-1", seats[9:], city="hudrosia", phase="1"),
    ]
    for aid in aids:
        played.press(slug, "deal", aid)
        played.press(slug, "start_meeting", aid)
    with factory() as session:
        room = session.query(Room).filter_by(code=played.code).one()
        log = RoomLog(session, room)
        who = Viewer.__new__(Viewer)
        who.room, who.log, who.seat_id, who.is_facilitator = room, log, "seat-1", True
        from sandbox.web.debrief import _context

        tables = [_context(log, aid, who) for aid in aids]
        group = ClassGroup(
            id="class-1", kind=slug, title="Democracy Simulation", tables=tuple(aids)
        )
        sections = CLASS_DEBRIEFS[slug](
            ClassContext(game=GAMES[slug], group=group, tables=tables, final=log.final)
        )

    assert sections[0].title == "The cities side by side"
    block = sections[0].blocks[0]
    assert block.columns == ("Democracies", "Oligarchies")
    assert "No proposal passed." in block.rows[0][0]
    assert "No proposal passed." in block.rows[0][1]


def test_the_value_cards_class_page_pools_the_trios(
    factory: sessionmaker[Session],
) -> None:
    from sandbox.model import AssignClassTables, StartClass

    slug = "value-cards-trading"
    played = Played(factory, ["Ada", "B1", "B2", "B3", "C1", "C2", "C3"])
    played.do(
        "seat-1",
        StartClass(
            kind=slug,
            title="Value Cards Trading",
            min_players=3,
            max_players=3,
            tables=2,
        ),
    )
    table = played.table()
    class_id = next(iter(table.classes))
    played.do(
        "seat-1",
        AssignClassTables(
            class_id, (("seat-2", "seat-3", "seat-4"), ("seat-5", "seat-6", "seat-7"))
        ),
    )
    first, second = table.classes[class_id].tables
    for aid in (first, second):
        built = build_activity_start(GAMES[slug], played.table(), "seat-1", aid)
        assert isinstance(built, Transaction), built
        played.do("seat-1", built)
        played.press(slug, "deal", aid)
    table = played.table()
    give = table.pieces_in_zone(f"{first}:hand-seat-2")[0].id
    want = table.pieces_in_zone(f"{first}:hand-seat-3")[0].id
    offer = OfferSwap(to_seat="seat-3", give=(give,), want=(want,))
    played.do("seat-2", offer)
    played.do("seat-3", AcceptSwap(offer_id=offer.op_id))

    page = played.get("Ada", f"/t/{played.code}/class/{class_id}/debrief").text

    assert "Values kept most often" in page
    assert "Values given away most often" in page
    assert "no trio is compared with another" in page
    assert "Across 2 trio(s)" in page


def test_nothing_in_a_democracy_export_names_a_person_when_anonymised(
    factory: sessionmaker[Session],
) -> None:
    played, _, _ = _democracy(factory, "potamosia", 9)

    body = played.get(
        "Ada", f"/t/{played.code}/record.json?anonymise=true&include_text=true"
    ).text

    for name in ("Ada", "Bea", "Cy", "Di"):
        assert f'"{name}"' not in body
    without = played.get("Ada", f"/t/{played.code}/record.json").text
    assert "Build the dam" not in without  # a proposal's text is written text
