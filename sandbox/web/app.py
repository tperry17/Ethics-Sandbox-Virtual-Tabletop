"""FastAPI application entry point."""

import asyncio
import contextlib
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import anyio.from_thread
from fastapi import (
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    Response,
    WebSocket,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from sandbox.content_loading import CONTENT_ROOT
from sandbox.db import Room, init_db, session_scope
from sandbox.games import EXERCISES, EXERCISES_BY_SLUG, GAMES, Exercise
from sandbox.games.loader import IMAGE_SUFFIXES, Card, Game
from sandbox.games.room_types import room_for_exercise, room_types
from sandbox.web.content import HELP_RECORDS, SITE_COPY
from sandbox.web.debrief import router as debrief_router
from sandbox.web.deps import get_session as get_session
from sandbox.web.identity import (
    new_participant_id,
    read_participant_cookie,
    set_participant_cookie,
)
from sandbox.web.live import hub
from sandbox.web.preview import table_preview as picture_of_table
from sandbox.web.record import build_record, record_zip
from sandbox.web.rooms import (
    FacilitatorTakenError,
    RoomClosedError,
    RoomNotFoundError,
    delete_room_record,
    get_participant,
    get_room_by_code,
    is_dormant,
    join_room,
    load_table,
    max_seats,
    open_room,
    purge_date,
    purge_expired,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


SWEEP_EVERY_SECONDS = 3600


def _purge_once() -> list[str]:
    with session_scope() as session:
        return purge_expired(session)


async def _sweep_forever() -> None:
    """Delete rooms idle for thirty days, at start and then every hour."""
    while True:
        for code in await asyncio.to_thread(_purge_once):
            await hub.close_room(code)
        await asyncio.sleep(SWEEP_EVERY_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Ensure the schema exists on startup. A no-op against a migrated database."""
    init_db()
    sweeper = asyncio.create_task(_sweep_forever())
    yield
    sweeper.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sweeper
    await hub.shutdown()


app = FastAPI(title="Ethics Sandbox", lifespan=lifespan)
app.include_router(debrief_router)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=PROJECT_ROOT / "sandbox" / "web" / "templates")


def _public_base(request: Request) -> str:
    """The address to put in every link people share.

    ``SANDBOX_PUBLIC_URL`` (set by scripts/deploy.sh from the Mac's network
    address) wins; otherwise the address this request arrived at.
    """
    configured = os.environ.get("SANDBOX_PUBLIC_URL", "").strip().rstrip("/")
    return configured or str(request.base_url).rstrip("/")


_ERROR_WORDS: dict[int, tuple[str, str]] = {
    403: (
        "You can't open that yet",
        "The message above says why. If you are not in the room, join it with "
        "its code. If it is for the facilitator, ask them.",
    ),
    410: (
        "This room is closed",
        "Its table can no longer be changed. If you facilitated it, the debrief "
        "and record are still yours to open. Otherwise ask for a new room code.",
    ),
    404: (
        "We couldn't find that",
        "Check the room code for typing mistakes, or ask whoever shared it for "
        "the link again. A room that nobody used for thirty days is deleted.",
    ),
}


def _wants_html(request: Request) -> bool:
    path = request.url.path
    if path.endswith((".json", ".zip")):
        return False
    return "text/html" in request.headers.get("accept", "text/html")


@app.exception_handler(StarletteHTTPException)
async def http_error_page(request: Request, error: StarletteHTTPException) -> Response:
    """Say what happened and what to do next, on pages; plain JSON elsewhere."""
    if not _wants_html(request):
        return Response(
            json.dumps({"detail": error.detail}),
            status_code=error.status_code,
            media_type="application/json",
        )
    heading, advice = _ERROR_WORDS.get(
        error.status_code,
        ("Something went wrong", "Try again, or go back to the start page."),
    )
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "heading": heading,
            "what_happened": error.detail,
            "advice": advice,
        },
        status_code=error.status_code,
    )


@app.exception_handler(Exception)
async def server_error_page(request: Request, _error: Exception) -> Response:
    """An unexpected failure: nothing is lost, and the table is saved."""
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "heading": "The server hit a problem",
            "what_happened": "Something went wrong on our side.",
            "advice": "Wait a few seconds and reload. Tables are saved as they go, "
            "so nothing on the table is lost. If it keeps happening, tell "
            "whoever is running the server.",
        },
        status_code=500,
    )


@app.get("/health", response_class=HTMLResponse)
async def health(request: Request) -> HTMLResponse:
    """A page anyone can open to check they can reach the server at all."""
    return templates.TemplateResponse(
        request=request,
        name="health.html",
        context={"address": _public_base(request)},
    )


def _identify(request: Request) -> str:
    """The caller's participant id, minting a fresh one if this is a first visit.

    The id is not written to a cookie here - identity.md's own contract is
    that a cookie is only ever set on the response actually being returned,
    so every route that calls this must also call ``set_participant_cookie``
    on its final response before returning it.
    """
    cookie_id = read_participant_cookie(request)
    return cookie_id if cookie_id is not None else new_participant_id()


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """Serve the seal at the path browsers request on their own, outside any page."""
    return FileResponse(PROJECT_ROOT / "static" / "icons" / "favicon.ico")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Render the project landing page."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "project_name": "Ethics Sandbox",
            "site_copy": SITE_COPY,
            "exercises": EXERCISES,
            "room_kinds": [
                {"slug": game.slug, "label": game.definition.room.label}
                for game in room_types(GAMES, [e.slug for e in EXERCISES])
                if game.definition.room is not None
            ],
            "canonical_url": _public_base(request) + "/",
            "og_image": _public_base(request) + "/static/og/default.png",
        },
    )


@app.get("/help", response_class=HTMLResponse)
async def help_page(request: Request) -> HTMLResponse:
    """Render the Help page: how rooms, records, export and deletion work."""
    return templates.TemplateResponse(
        request=request, name="help.html", context={"records": HELP_RECORDS}
    )


@app.get("/exercises/{slug}", response_class=HTMLResponse)
async def exercise_detail(request: Request, slug: str) -> HTMLResponse:
    """Render the catalog page for a single exercise."""
    exercise = EXERCISES_BY_SLUG.get(slug)
    if exercise is None:
        raise HTTPException(status_code=404, detail="No such exercise.")
    game = GAMES.get(slug)
    return templates.TemplateResponse(
        request=request,
        name="exercise.html",
        context={
            "exercise": exercise,
            "site_copy": SITE_COPY,
            "room_kind": None
            if (room_game := room_for_exercise(GAMES, slug)) is None
            else room_game.slug,
            "canonical_url": f"{_public_base(request)}/exercises/{slug}",
            "og_image": f"{_public_base(request)}/static/og/{slug}.png",
            "preview": None if game is None else picture_of_table(game),
            "has_deck": game is not None and bool(_printable_decks(game)),
        },
    )


def _printable_decks(game: Game) -> list[tuple[Card, ...]]:
    """The decks an exercise's print page shows.

    A deck marked revealable: false is private for the whole session, so the
    public page never prints it.
    """
    return [
        game.decks[deck.id]
        for deck in game.definition.components.decks
        if deck.revealable and game.decks[deck.id]
    ]


@app.get("/exercises/{slug}/deck", response_class=HTMLResponse)
async def exercise_deck(request: Request, slug: str) -> HTMLResponse:
    """Every card of an exercise's decks, laid out to print and cut out."""
    game = GAMES.get(slug)
    shown = [] if game is None else _printable_decks(game)
    if game is None or not shown:
        raise HTTPException(status_code=404, detail="That exercise has no deck.")
    return templates.TemplateResponse(
        request=request,
        name="deck.html",
        context={"game": game, "decks": shown},
    )


@app.get("/games/{slug}/preview", response_class=HTMLResponse)
async def game_preview(request: Request, slug: str) -> HTMLResponse:
    """The table of any game definition after setup, as a still picture."""
    game = GAMES.get(slug)
    if game is None:
        raise HTTPException(status_code=404, detail="No such game.")
    return templates.TemplateResponse(
        request=request,
        name="game_preview.html",
        context={"game": game, "preview": picture_of_table(game)},
    )


@app.get("/content/{path:path}")
async def content_image(path: str) -> FileResponse:
    """An image under ``content/`` - a card or role drawn from a picture.

    Only image files are served, and only from inside ``content/``: the CSV
    files beside them hold whole decks, which a browser must never be able
    to fetch.
    """
    root = CONTENT_ROOT.resolve()
    file = (root / path).resolve()
    if (
        not file.is_relative_to(root)
        or file.suffix.lower() not in IMAGE_SUFFIXES
        or not file.is_file()
    ):
        raise HTTPException(status_code=404, detail="No such image.")
    return FileResponse(file)


@app.post("/rooms")
def open_room_route(
    request: Request,
    kind: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    """Open a room of one kind, then send its opener to the join form.

    Only the room types' own buttons post here (an exercise page's "Open a
    room" and the landing page's menu); there is no page for it. Whoever
    opened the room joins it like anyone else, with a display name.
    """
    cookie_id = _identify(request)
    game = GAMES.get(kind)
    if game is None or game.definition.room is None:
        raise HTTPException(status_code=404, detail="There is no such kind of room.")
    room = open_room(session, game_slug=game.slug)
    response: Response = RedirectResponse(
        url=f"/join?code={room.code}", status_code=303
    )
    set_participant_cookie(response, request, cookie_id)
    return response


def _join_exercise(session: Session, exercise: str, code: str) -> Exercise | None:
    """The exercise whose page the join form links back to, if there is one.

    An exercise page's "Join a room" names its exercise; otherwise a code
    that names a room gives the exercise that room type belongs to.
    """
    if exercise in EXERCISES_BY_SLUG:
        return EXERCISES_BY_SLUG[exercise]
    room = get_room_by_code(session, code) if code.strip() else None
    game = GAMES.get(room.game_slug) if room is not None else None
    if game is None or game.definition.room is None:
        return None
    return EXERCISES_BY_SLUG.get(game.definition.room.exercise)


@app.get("/join", response_class=HTMLResponse)
def join_form(
    request: Request,
    code: str = "",
    exercise: str = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Render the form for entering a room code and display name."""
    return templates.TemplateResponse(
        request=request,
        name="join.html",
        context={
            "error": None,
            "code": code,
            "display_name": "",
            "exercise": _join_exercise(session, exercise, code),
        },
    )


@app.post("/join", response_class=HTMLResponse)
def join_room_route(
    request: Request,
    room_code: str = Form(...),
    display_name: str = Form(...),
    as_facilitator: bool = Form(False),
    exercise: str = Form(""),
    session: Session = Depends(get_session),
) -> Response:
    """Seat the caller at the room named by ``room_code``."""
    cookie_id = _identify(request)

    def _error(message: str) -> Response:
        response = templates.TemplateResponse(
            request=request,
            name="join.html",
            status_code=400,
            context={
                "error": message,
                "code": room_code,
                "display_name": display_name,
                "exercise": _join_exercise(session, exercise, room_code),
            },
        )
        set_participant_cookie(response, request, cookie_id)
        return response

    if not room_code.strip():
        return _error("Enter a room code.")
    if not display_name.strip():
        return _error("Enter a name to join with.")

    try:
        participant = join_room(
            session,
            code=room_code,
            cookie_id=cookie_id,
            display_name=display_name,
            as_facilitator=as_facilitator,
        )
    except RoomNotFoundError:
        return _error(
            f"There is no room with the code {room_code.strip().upper()!r}. "
            "Check the code for typing mistakes, or ask for it again."
        )
    except RoomClosedError:
        return _error(
            "That room is closed, so no one can join it. "
            "Ask the facilitator for a new room code."
        )
    except FacilitatorTakenError:
        return _error("That room already has a facilitator. Join as a player.")
    if participant.seat_id is not None:
        # Committed first, so a live room that reads the seat finds it.
        session.commit()
        anyio.from_thread.run(hub.seat_taken, room_code.strip().upper(), participant.id)

    response = RedirectResponse(url=f"/t/{room_code.strip().upper()}", status_code=303)
    set_participant_cookie(response, request, cookie_id)
    return response


@app.get("/t/{code}", response_class=HTMLResponse)
def table_shell(
    request: Request, code: str, session: Session = Depends(get_session)
) -> Response:
    """Render the table page shell: header, seat roster, and the client mount point."""
    room = get_room_by_code(session, code)
    if room is None:
        raise HTTPException(status_code=404, detail="No such room.")
    if room.status == "closed":
        raise HTTPException(status_code=410, detail="This room is closed.")

    cookie_id = read_participant_cookie(request)
    participant = get_participant(session, room.id, cookie_id) if cookie_id else None
    if participant is None:
        return RedirectResponse(url=f"/join?code={room.code}", status_code=307)

    exercise = EXERCISES_BY_SLUG.get(room.game_slug)
    game = GAMES.get(room.game_slug)
    if exercise is not None:
        title = exercise.title
    elif game is not None:
        title = game.title
    else:
        title = room.game_slug
    table = load_table(session, room)
    seats = sorted(table.seats.values(), key=lambda seat: seat.id)
    participants_by_seat = {
        other.seat_id: other for other in room.participants if other.seat_id is not None
    }
    observers = [other for other in room.participants if other.is_observer]
    is_facilitator = participant.seat_id is not None and table.is_facilitator(
        participant.seat_id
    )

    return templates.TemplateResponse(
        request=request,
        name="table.html",
        context={
            "room": room,
            "exercise": exercise,
            "title": title,
            "participant": participant,
            "seats": seats,
            "participants_by_seat": participants_by_seat,
            "observers": observers,
            "is_facilitator": is_facilitator,
            "invite_url": f"{_public_base(request)}/join?code={room.code}",
            "dormant": is_dormant(room),
            "purge_date": purge_date(room),
            "max_seats": max_seats(room),
        },
    )


def _facilitator_room(request: Request, code: str, session: Session) -> Room:
    """The room, if the caller is its facilitator; otherwise a 404 or 403."""
    room = get_room_by_code(session, code)
    if room is None:
        raise HTTPException(status_code=404, detail="No such room.")
    cookie_id = read_participant_cookie(request)
    participant = get_participant(session, room.id, cookie_id) if cookie_id else None
    seat_id = participant.seat_id if participant is not None else None
    if seat_id is None or not load_table(session, room).is_facilitator(seat_id):
        raise HTTPException(
            status_code=403, detail="Only the facilitator can open the record."
        )
    return room


def _export(
    session: Session, room: Room, anonymise: bool, include_text: bool
) -> dict[str, object]:
    return build_record(
        session,
        room,
        anonymise=anonymise,
        include_text=include_text,
        exported_at=datetime.now(UTC),
    )


@app.get("/t/{code}/record.json")
def record_json(
    request: Request,
    code: str,
    anonymise: bool = False,
    include_text: bool = False,
    session: Session = Depends(get_session),
) -> Response:
    """The room's event log as JSON, for the facilitator."""
    room = _facilitator_room(request, code, session)
    body = json.dumps(_export(session, room, anonymise, include_text), indent=2)
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{room.code}.json"'},
    )


@app.get("/t/{code}/record.zip")
def record_csv(
    request: Request,
    code: str,
    anonymise: bool = False,
    include_text: bool = False,
    session: Session = Depends(get_session),
) -> Response:
    """The room's event log as one CSV per event type, zipped."""
    room = _facilitator_room(request, code, session)
    body = record_zip(_export(session, room, anonymise, include_text))
    return Response(
        body,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{room.code}.zip"'},
    )


@app.post("/t/{code}/record/delete")
def record_delete(
    request: Request,
    code: str,
    session: Session = Depends(get_session),
) -> Response:
    """Delete the room and everything recorded in it, for the facilitator."""
    room = _facilitator_room(request, code, session)
    code = room.code
    delete_room_record(session, room)
    session.commit()
    anyio.from_thread.run(hub.close_room, code)
    return RedirectResponse(url="/", status_code=303)


@app.websocket("/ws/t/{code}")
async def table_socket(websocket: WebSocket, code: str) -> None:
    """The live table socket. Transport only - every rule lives in the model."""
    await hub.serve(websocket, code)


@app.get("/table-preview", response_class=HTMLResponse)
async def table_preview(
    request: Request, pieces: int = 0, measure: bool = False, loop: bool = False
) -> HTMLResponse:
    """The table client driven by a recorded session, with no room behind it.

    The rendering half of the client is developed and tested against this
    page: it replays a recorded session in the browser, so a table can be
    looked at, and its frame rate measured with ``?pieces=300&measure=1``,
    without a room, a socket, or a database. Like ``/styleguide``, it shows
    only fixture material and reaches no room's state.
    """
    return templates.TemplateResponse(
        request=request,
        name="table_preview.html",
        context={
            "pieces": max(0, min(pieces, 2000)),
            "measure": measure,
            "loop": loop,
        },
    )


@app.get("/styleguide", response_class=HTMLResponse)
async def styleguide(request: Request) -> HTMLResponse:
    """Render the complete design-system reference page."""
    color_tokens = [
        {
            "label": "Surfaces",
            "tokens": [
                {"name": "--surface-page"},
                {"name": "--surface-raised"},
                {"name": "--surface-sunken"},
                {"name": "--surface-border"},
                {"name": "--surface-border-strong"},
            ],
        },
        {
            "label": "Table",
            "tokens": [
                {"name": "--table-felt", "inverse": True},
                {"name": "--table-felt-edge", "inverse": True},
                {"name": "--table-zone-outline"},
                {"name": "--table-zone-private", "inverse": True},
                {"name": "--table-drop-target"},
                {"name": "--card-back", "inverse": True},
                {"name": "--card-back-edge"},
                {"name": "--card-back-ink"},
            ],
        },
        {
            "label": "Text & rubric",
            "tokens": [
                {"name": "--text-primary", "inverse": True},
                {"name": "--text-secondary", "inverse": True},
                {"name": "--text-muted", "inverse": True},
                {"name": "--text-inverse"},
                {"name": "--accent-rubric", "inverse": True},
                {"name": "--accent-rubric-soft"},
            ],
        },
        {
            "label": "Semantic · game state only",
            "tokens": [
                {"name": "--semantic-assent", "inverse": True},
                {"name": "--semantic-tension", "inverse": True},
                {"name": "--semantic-caution", "inverse": True},
            ],
        },
        {
            "label": "Seats",
            "tokens": [{"name": f"--seat-{seat}"} for seat in range(1, 7)]
            + [{"name": "--seat-ink", "inverse": True}],
        },
        {
            "label": "Supporting colour",
            "tokens": [
                {"name": "--overlay", "inverse": True},
                {"name": "--shadow-color", "inverse": True},
                {"name": "--shadow-color-strong", "inverse": True},
                {"name": "--transparent"},
            ],
        },
    ]
    return templates.TemplateResponse(
        request=request,
        name="styleguide.html",
        context={
            "color_tokens": color_tokens,
            "space_tokens": [f"--space-{step}" for step in range(1, 9)],
            "foundation_tokens": [
                "--font-reading",
                "--font-ui",
                "--font-mono",
                "--text-xs",
                "--text-sm",
                "--text-md",
                "--text-lg",
                "--text-xl",
                "--text-2xl",
                "--text-3xl",
                "--leading-tight",
                "--leading-reading",
                "--tracking-label",
                "--measure-reading",
                "--radius-sm",
                "--radius-md",
                "--radius-lg",
                "--line-hairline",
                "--line-strong",
                "--shadow-raised",
                "--shadow-piece",
                "--focus-ring",
            ],
        },
    )
