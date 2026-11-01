"""The debrief, the replay and the reflection page.

Everything here reads the room's event log (and rebuilds its table from it);
none of it records anything new about what people do at the table. The two
things it does write are the facilitator's observation notes (kept in the log
as a ``Record`` with no effect on the table) and a participant's own written
answers (kept in ``reflections``, private unless they share one).

A debrief is keyed by an activity or a class of the room, because a room holds
many. The facilitator sees it at any time; everyone else sees it once the
facilitator opens it. It never ranks people and never says which choice was
right; for what was said on the call there are only the facilitator's notes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sandbox.db.models import Participant, Reflection, Room
from sandbox.games import GAMES
from sandbox.games.content import load_exercise
from sandbox.games.debrief import (
    ACTIVITY_DEBRIEFS,
    CLASS_DEBRIEFS,
    ClassContext,
    Context,
    Entry,
    Section,
    leaf_entries,
)
from sandbox.games.loader import Face
from sandbox.model import Activity, ClassGroup, Record, Table
from sandbox.web.deps import get_session
from sandbox.web.identity import read_participant_cookie
from sandbox.web.preview import table_picture
from sandbox.web.replay import LogEvent, load_events, replay, seed_of
from sandbox.web.rooms import append_event, get_participant, get_room_by_code

PROJECT_ROOT = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=PROJECT_ROOT / "sandbox" / "web" / "templates")
router = APIRouter()

OBSERVATION = "observation"


class RoomLog:
    """A room's log, read once, with the tables it rebuilds."""

    def __init__(self, session: Session, room: Room) -> None:
        self.room = room
        self.events: list[LogEvent] = load_events(session, room)
        self.entries: list[Entry] = leaf_entries(self.events)
        self.seed = seed_of(session, room)
        self.final: Table = replay(self.events, self.seed).table
        self._at: dict[int, Table] = {}
        people = session.execute(
            select(Participant).where(Participant.room_id == room.id)
        ).scalars()
        self.people = list(people)
        self.names: dict[str, str] = {
            p.seat_id: p.display_name for p in self.people if p.seat_id is not None
        }

    def table_at(self, seq: int) -> Table:
        if seq not in self._at:
            self._at[seq] = replay(self.events, self.seed, upto=seq).table
        return self._at[seq]

    def _end_seq(self, op_type: str, field_name: str, key: str) -> int | None:
        for entry in self.entries:
            if entry.op_type == op_type and entry.payload.get(field_name) == key:
                return entry.seq
        return None

    def activity_ids(self) -> list[str]:
        """Every activity the log mentions, in the order it first appears."""
        found: list[str] = []
        for entry in self.entries:
            candidates = [entry.activity_id]
            if entry.op_type in ("BeginActivity", "EndActivity", "JoinActivity"):
                candidates.append(str(entry.payload.get("activity_id", "")))
            for candidate in candidates:
                if candidate and candidate not in found:
                    found.append(candidate)
        return found

    def class_ids(self) -> list[str]:
        found: list[str] = []
        for entry in self.entries:
            key = str(entry.payload.get("class_id", ""))
            if key and entry.op_type != "Spawn" and key not in found:
                found.append(key)
        return found

    def activity(self, activity_id: str) -> tuple[Activity, Table] | None:
        """The activity and the table as it stood when it was last there."""
        table = self.final
        if activity_id not in table.activities:
            end = self._end_seq("EndActivity", "activity_id", activity_id)
            if end is None:
                return None
            table = self.table_at(end - 1)
        found = table.activities.get(activity_id)
        return None if found is None else (found, table)

    def group(self, class_id: str) -> tuple[ClassGroup, Table] | None:
        table = self.final
        if class_id not in table.classes:
            end = self._end_seq("EndClass", "class_id", class_id)
            if end is None:
                return None
            table = self.table_at(end - 1)
        found = table.classes.get(class_id)
        return None if found is None else (found, table)

    def started_at(self, activity_id: str) -> datetime | None:
        for entry in self.entries:
            if entry.macro == f"activity:{activity_id}":
                return entry.at
        return None


class Viewer:
    """Who is asking: a person in the room, and whether they are its facilitator."""

    def __init__(self, session: Session, request: Request, code: str) -> None:
        room = get_room_by_code(session, code)
        if room is None:
            raise HTTPException(status_code=404, detail="No such room.")
        cookie_id = read_participant_cookie(request)
        participant = (
            get_participant(session, room.id, cookie_id) if cookie_id else None
        )
        if participant is None:
            raise HTTPException(status_code=403, detail="Join the room first.")
        self.room = room
        self.participant = participant
        self.log = RoomLog(session, room)
        self.seat_id = participant.seat_id
        self.is_facilitator = (
            self.seat_id is not None and self.log.final.is_facilitator(self.seat_id)
        )

    def require_facilitator(self) -> None:
        if not self.is_facilitator:
            raise HTTPException(
                status_code=403, detail="Only the facilitator can do that."
            )


def viewer(
    request: Request, code: str, session: Session = Depends(get_session)
) -> Viewer:
    return Viewer(session, request, code)


# -- the facilitator's choices, kept on the room -------------------------------------


def settings_for(room: Room, key: str) -> dict[str, Any]:
    stored = room.config.get("debrief")
    if isinstance(stored, dict) and isinstance(stored.get(key), dict):
        return dict(stored[key])
    return {}


def save_settings(room: Room, key: str, values: Mapping[str, Any]) -> None:
    stored = dict(room.config.get("debrief") or {})  # type: ignore[call-overload]
    stored[key] = {**settings_for(room, key), **values}
    room.config = {**room.config, "debrief": stored}


# -- observation notes ---------------------------------------------------------------


def notes_for(log: RoomLog, key: str) -> list[dict[str, str]]:
    return [
        {
            "when": entry.at.strftime("%H:%M"),
            "text": str(entry.payload["data"].get("text", "")),
            "outcome": str(entry.payload["data"].get("outcome", "")),
        }
        for entry in log.entries
        if entry.op_type == "Record"
        and entry.payload["label"] == OBSERVATION
        and entry.payload["data"].get("scope") == key
    ]


# -- building a page -----------------------------------------------------------------


def _context(log: RoomLog, activity_id: str, who: Viewer) -> Context:
    found = log.activity(activity_id)
    if found is None:
        raise HTTPException(status_code=404, detail="No such activity.")
    activity, table = found
    game = GAMES[activity.kind]
    return Context(
        game=game,
        activity=activity,
        entries=log.entries,
        final=table,
        table_at=log.table_at,
        names=log.names,
        viewer_seat=who.seat_id,
        is_facilitator=who.is_facilitator,
        settings=settings_for(who.room, activity_id),
        started_at=log.started_at(activity_id),
    )


def _outcome_titles(kind: str) -> list[str]:
    try:
        return [o.title for o in load_exercise(kind).learning_outcomes]
    except KeyError:
        return []


def _page(
    request: Request,
    who: Viewer,
    *,
    key: str,
    title: str,
    kind: str,
    sections: list[Section],
    is_class: bool,
) -> Response:
    settings = settings_for(who.room, key)
    if not who.is_facilitator and not settings.get("open"):
        raise HTTPException(
            status_code=403, detail="The facilitator has not opened this debrief."
        )
    reflections = [row for row in _shared_reflections(who, key)]
    return templates.TemplateResponse(
        request=request,
        name="debrief.html",
        context={
            "room": who.room,
            "title": title,
            "sections": sections,
            "key": key,
            "is_class": is_class,
            "is_facilitator": who.is_facilitator,
            "open": bool(settings.get("open")),
            "show_council_votes": bool(settings.get("show_council_votes")),
            "has_council": kind == "democracy-simulation",
            "outcomes": _outcome_titles(kind),
            "notes": notes_for(who.log, key) if who.is_facilitator else [],
            "reflections": reflections,
        },
    )


def _shared_reflections(who: Viewer, key: str) -> list[dict[str, str]]:
    """What people chose to share with the table, without their names."""
    session = Session.object_session(who.room)
    if session is None:
        return []
    game_prompts: dict[str, str] = {}
    for game in GAMES.values():
        for prompt in game.prompts:
            game_prompts[prompt.id] = prompt.text
    rows = session.execute(
        select(Reflection)
        .where(Reflection.room_id == who.room.id, Reflection.visibility == "shared")
        .order_by(Reflection.created_at)
    ).scalars()
    found: list[dict[str, str]] = []
    for row in rows:
        scope, _, prompt_id = row.prompt_key.partition("/")
        if scope == key:
            found.append(
                {"prompt": game_prompts.get(prompt_id, prompt_id), "body": row.body}
            )
    return found


@router.get("/t/{code}/debrief", response_class=HTMLResponse)
def debrief_index(request: Request, who: Viewer = Depends(viewer)) -> Response:
    """The room's activities and classes that have a debrief."""
    log = who.log
    rows: list[dict[str, Any]] = []
    for activity_id in log.activity_ids():
        found = log.activity(activity_id)
        if found is None or found[0].kind not in ACTIVITY_DEBRIEFS:
            continue
        activity = found[0]
        if activity.class_id:
            continue
        rows.append(
            {
                "title": activity.title,
                "href": f"/t/{who.room.code}/debrief/{activity_id}",
                "open": bool(settings_for(who.room, activity_id).get("open")),
            }
        )
    for class_id in log.class_ids():
        found_group = log.group(class_id)
        if found_group is None or found_group[0].kind not in CLASS_DEBRIEFS:
            continue
        group, table = found_group
        rows.append(
            {
                "title": f"{group.title} (a class of {len(group.tables)} tables)",
                "href": f"/t/{who.room.code}/class/{class_id}/debrief",
                "open": bool(settings_for(who.room, class_id).get("open")),
            }
        )
        for table_id in group.tables:
            inner = log.activity(table_id)
            if inner is not None:
                rows.append(
                    {
                        "title": f"  {inner[0].title}",
                        "href": f"/t/{who.room.code}/debrief/{table_id}",
                        "open": bool(settings_for(who.room, table_id).get("open")),
                    }
                )
    if not who.is_facilitator:
        rows = [row for row in rows if row["open"]]
    return templates.TemplateResponse(
        request=request,
        name="debrief_index.html",
        context={"room": who.room, "rows": rows, "is_facilitator": who.is_facilitator},
    )


@router.get("/t/{code}/debrief/{activity_id}", response_class=HTMLResponse)
def debrief_activity(
    request: Request, activity_id: str, who: Viewer = Depends(viewer)
) -> Response:
    context = _context(who.log, activity_id, who)
    builder = ACTIVITY_DEBRIEFS.get(context.activity.kind)
    if builder is None:
        raise HTTPException(status_code=404, detail="This activity has no debrief yet.")
    return _page(
        request,
        who,
        key=activity_id,
        title=_title(context.activity),
        kind=context.activity.kind,
        sections=builder(context),
        is_class=False,
    )


def _title(activity: Activity) -> str:
    city = activity.options.get("city")
    return f"{activity.title}: {city.title()}" if city else activity.title


@router.get("/t/{code}/class/{class_id}/debrief", response_class=HTMLResponse)
def debrief_class(
    request: Request, class_id: str, who: Viewer = Depends(viewer)
) -> Response:
    found = who.log.group(class_id)
    if found is None:
        raise HTTPException(status_code=404, detail="No such class.")
    group, table = found
    builder = CLASS_DEBRIEFS.get(group.kind)
    if builder is None:
        raise HTTPException(status_code=404, detail="This class has no debrief yet.")
    tables = [_context(who.log, table_id, who) for table_id in group.tables] + [
        _context(who.log, aid, who)
        for aid in who.log.activity_ids()
        if (found_one := who.log.activity(aid)) is not None
        and found_one[0].class_id == class_id
        and aid not in group.tables
    ]
    context = ClassContext(
        game=GAMES[group.kind], group=group, tables=tables, final=table
    )
    return _page(
        request,
        who,
        key=class_id,
        title=group.title,
        kind=group.kind,
        sections=builder(context),
        is_class=True,
    )


def _back(code: str, key: str, is_class: bool) -> RedirectResponse:
    where = f"/t/{code}/class/{key}/debrief" if is_class else f"/t/{code}/debrief/{key}"
    return RedirectResponse(url=where, status_code=303)


@router.post("/t/{code}/debrief/{key}/open")
def debrief_open(
    key: str,
    is_class: bool = Form(False),
    opened: bool = Form(False),
    who: Viewer = Depends(viewer),
    session: Session = Depends(get_session),
) -> Response:
    who.require_facilitator()
    room = session.merge(who.room)
    save_settings(room, key, {"open": opened})
    return _back(room.code, key, is_class)


@router.post("/t/{code}/debrief/{key}/settings")
def debrief_settings(
    key: str,
    is_class: bool = Form(False),
    show_council_votes: bool = Form(False),
    surfaced: list[str] = Form(default_factory=list),
    which: str = Form("council"),
    who: Viewer = Depends(viewer),
    session: Session = Depends(get_session),
) -> Response:
    who.require_facilitator()
    room = session.merge(who.room)
    values: dict[str, Any] = (
        {"surfaced": surfaced}
        if which == "surfaced"
        else {"show_council_votes": show_council_votes}
    )
    save_settings(room, key, values)
    return _back(room.code, key, is_class)


@router.post("/t/{code}/debrief/{key}/note")
def debrief_note(
    key: str,
    text: str = Form(...),
    outcome: str = Form(""),
    is_class: bool = Form(False),
    who: Viewer = Depends(viewer),
    session: Session = Depends(get_session),
) -> Response:
    """An observation note, kept in the room's log, tagged with an outcome."""
    who.require_facilitator()
    if not text.strip():
        return _back(who.room.code, key, is_class)
    room = session.merge(who.room)
    record = Record(
        label=OBSERVATION,
        data={"scope": key, "text": text.strip(), "outcome": outcome},
    )
    for attempt in range(3):
        try:
            with session.begin_nested():
                append_event(session, room, actor_seat=who.seat_id, op=record)
            break
        except IntegrityError:
            if attempt == 2:
                raise
    return _back(room.code, key, is_class)


# -- replay --------------------------------------------------------------------------


def _faces() -> dict[str, Face]:
    faces: dict[str, Face] = {}
    for game in GAMES.values():
        faces.update(game.faces())
    return faces


@router.get("/t/{code}/replay", response_class=HTMLResponse)
def replay_page(request: Request, who: Viewer = Depends(viewer)) -> Response:
    """The table rebuilt from the log, with a scrubber. Read-only."""
    who.require_facilitator()
    steps = []
    first = who.log.events[0].created_at if who.log.events else None
    for event in who.log.events:
        label = (
            str(event.payload.get("label") or event.payload.get("name") or "")
            if event.op_type == "Transaction"
            else event.op_type
        )
        offset = (event.created_at - first).total_seconds() if first else 0.0
        steps.append({"seq": event.seq, "label": label, "offset": int(offset)})
    return templates.TemplateResponse(
        request=request,
        name="replay.html",
        context={"room": who.room, "steps": json.dumps(steps), "count": len(steps)},
    )


@router.get("/t/{code}/replay/frame", response_class=HTMLResponse)
def replay_frame(
    request: Request,
    seq: int,
    faces: bool = False,
    who: Viewer = Depends(viewer),
) -> Response:
    """The table after event ``seq``: the public view, or every face."""
    who.require_facilitator()
    table = who.log.table_at(seq)
    picture = table_picture(table, _faces(), "room", all_faces=faces)
    caption = (
        "Every face is showing."
        if faces
        else "The public view: faces nobody may see are drawn as backs."
    )
    return templates.TemplateResponse(
        request=request,
        name="_replay_frame.html",
        context={"preview": picture, "caption": caption},
    )


# -- reflection ----------------------------------------------------------------------


def _reflection_prompts(who: Viewer) -> list[dict[str, Any]]:
    """The prompts of every activity in the room that has some, by activity."""
    groups: list[dict[str, Any]] = []
    for activity_id in who.log.activity_ids():
        found = who.log.activity(activity_id)
        if found is None:
            continue
        game = GAMES.get(found[0].kind)
        if game is None or not game.prompts:
            continue
        groups.append(
            {
                "scope": activity_id,
                "title": _title(found[0]),
                "prompts": [(p.id, p.text) for p in game.prompts],
            }
        )
    return groups


@router.get("/t/{code}/reflect", response_class=HTMLResponse)
def reflect_page(
    request: Request,
    saved: bool = False,
    who: Viewer = Depends(viewer),
    session: Session = Depends(get_session),
) -> Response:
    """A private place to answer a prompt. It never blocks the table."""
    mine = session.execute(
        select(Reflection)
        .where(
            Reflection.room_id == who.room.id,
            Reflection.participant_id == who.participant.id,
        )
        .order_by(Reflection.created_at)
    ).scalars()
    return templates.TemplateResponse(
        request=request,
        name="reflect.html",
        context={
            "room": who.room,
            "groups": _reflection_prompts(who),
            "mine": [
                {"body": r.body, "shared": r.visibility == "shared"} for r in mine
            ],
            "saved": saved,
        },
    )


@router.post("/t/{code}/reflect")
def reflect_save(
    scope_prompt: str = Form(...),
    body: str = Form(...),
    share: bool = Form(False),
    who: Viewer = Depends(viewer),
    session: Session = Depends(get_session),
) -> Response:
    """Keep an answer, private unless its writer shares it with the table."""
    if body.strip():
        session.add(
            Reflection(
                room_id=who.room.id,
                participant_id=who.participant.id,
                prompt_key=scope_prompt,
                body=body.strip(),
                visibility="shared" if share else "private",
                created_at=datetime.now(UTC),
            )
        )
    return RedirectResponse(
        url=f"/t/{who.room.code}/reflect?saved=true", status_code=303
    )
