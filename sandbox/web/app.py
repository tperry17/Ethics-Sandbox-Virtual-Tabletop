"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sandbox.games import EXERCISES, EXERCISES_BY_SLUG
from sandbox.web.content import PRINCIPLES

PROJECT_ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(title="Ethics Sandbox")
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=PROJECT_ROOT / "sandbox" / "web" / "templates")


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
