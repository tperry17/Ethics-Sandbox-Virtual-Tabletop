"""FastAPI application entry point."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from sandbox.db import init_db, session_scope
from sandbox.games import EXERCISES, EXERCISES_BY_SLUG
from sandbox.web.content import PRINCIPLES
from sandbox.web.identity import (
    new_participant_id,
    read_participant_cookie,
    set_participant_cookie,
)
from sandbox.web.rooms import (
    RoomClosedError,
    RoomNotFoundError,
    UnknownExerciseError,
    create_room,
    get_participant,
    get_room_by_code,
    join_room,
    load_table,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Ensure the schema exists on startup. A no-op against a migrated database."""
    init_db()
    yield


app = FastAPI(title="Ethics Sandbox", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=PROJECT_ROOT / "sandbox" / "web" / "templates")


def get_session() -> Iterator[Session]:
    """One request-scoped database session, committed or rolled back for you."""
    with session_scope() as session:
        yield session


def _identify(request: Request) -> str:
    """The caller's participant id, minting a fresh one if this is a first visit.

    The id is not written to a cookie here - identity.md's own contract is
    that a cookie is only ever set on the response actually being returned,
    so every route that calls this must also call ``set_participant_cookie``
    on its final response before returning it.
    """
    cookie_id = read_participant_cookie(request)
    return cookie_id if cookie_id is not None else new_participant_id()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Render the project landing page."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "project_name": "Ethics Sandbox",
            "principles": PRINCIPLES,
            "exercises": EXERCISES,
        },
    )


@app.get("/exercises/{slug}", response_class=HTMLResponse)
async def exercise_detail(request: Request, slug: str) -> HTMLResponse:
    """Render the catalog page for a single exercise."""
    exercise = EXERCISES_BY_SLUG.get(slug)
    if exercise is None:
        raise HTTPException(status_code=404, detail="No such exercise.")
    return templates.TemplateResponse(
        request=request,
        name="exercise.html",
        context={"exercise": exercise},
    )


@app.get("/start", response_class=HTMLResponse)
async def start_form(request: Request) -> HTMLResponse:
    """Render the form for choosing an exercise and starting a room."""
    return templates.TemplateResponse(
        request=request,
        name="start.html",
        context={"exercises": EXERCISES, "error": None},
    )


@app.post("/start", response_class=HTMLResponse)
async def start_room(
    request: Request,
    game_slug: str = Form(...),
    display_name: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    """Create a room for ``game_slug`` and seat its facilitator."""
    cookie_id = _identify(request)

    if not display_name.strip():
        response: Response = templates.TemplateResponse(
            request=request,
            name="start.html",
            status_code=400,
            context={
                "exercises": EXERCISES,
                "error": "Enter a name for the facilitator.",
            },
        )
        set_participant_cookie(response, request, cookie_id)
        return response

    try:
        room, _facilitator = create_room(
            session,
            game_slug=game_slug,
            facilitator_cookie_id=cookie_id,
            facilitator_name=display_name,
        )
    except UnknownExerciseError:
        response = templates.TemplateResponse(
            request=request,
            name="start.html",
            status_code=400,
            context={
                "exercises": EXERCISES,
                "error": "Choose one of the exercises below.",
            },
        )
        set_participant_cookie(response, request, cookie_id)
        return response

    response = RedirectResponse(url=f"/t/{room.code}", status_code=303)
    set_participant_cookie(response, request, cookie_id)
    return response


@app.get("/join", response_class=HTMLResponse)
async def join_form(request: Request, code: str = "") -> HTMLResponse:
    """Render the form for entering a room code and display name."""
    return templates.TemplateResponse(
        request=request,
        name="join.html",
        context={"error": None, "code": code, "display_name": ""},
    )


@app.post("/join", response_class=HTMLResponse)
async def join_room_route(
    request: Request,
    room_code: str = Form(...),
    display_name: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    """Seat the caller at the room named by ``room_code``."""
    cookie_id = _identify(request)

    def _error(message: str) -> Response:
        response = templates.TemplateResponse(
            request=request,
            name="join.html",
            status_code=400,
            context={"error": message, "code": room_code, "display_name": display_name},
        )
        set_participant_cookie(response, request, cookie_id)
        return response

    if not room_code.strip():
        return _error("Enter a room code.")
    if not display_name.strip():
        return _error("Enter a name to join with.")

    try:
        join_room(
            session, code=room_code, cookie_id=cookie_id, display_name=display_name
        )
    except RoomNotFoundError:
        return _error(f"There is no room with the code {room_code.strip().upper()!r}.")
    except RoomClosedError:
        return _error("That room is closed.")

    response = RedirectResponse(url=f"/t/{room_code.strip().upper()}", status_code=303)
    set_participant_cookie(response, request, cookie_id)
    return response


@app.get("/t/{code}", response_class=HTMLResponse)
async def table_shell(
    request: Request, code: str, session: Session = Depends(get_session)
) -> Response:
    """Render the table page shell: header, seat roster, and the client mount point."""
    room = get_room_by_code(session, code)
    if room is None:
        raise HTTPException(status_code=404, detail="No such room.")

    cookie_id = read_participant_cookie(request)
    participant = get_participant(session, room.id, cookie_id) if cookie_id else None
    if participant is None:
        return RedirectResponse(url=f"/join?code={room.code}", status_code=307)

    exercise = EXERCISES_BY_SLUG.get(room.game_slug)
    table = load_table(session, room)
    seats = sorted(table.seats.values(), key=lambda seat: seat.id)
    participants_by_seat = {
        other.seat_id: other for other in room.participants if other.seat_id is not None
    }
    observers = [other for other in room.participants if other.is_observer]

    return templates.TemplateResponse(
        request=request,
        name="table.html",
        context={
            "room": room,
            "exercise": exercise,
            "participant": participant,
            "seats": seats,
            "participants_by_seat": participants_by_seat,
            "observers": observers,
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
            "tokens": [
                {"name": f"--seat-{seat}"} for seat in range(1, 7)
            ]
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
