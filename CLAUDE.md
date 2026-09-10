# Ethics Sandbox

## What it is

The Ethics Sandbox is a virtual tabletop for structured exercises about values, ethics, and democratic decision-making. A small group joins a room by link, sits at a shared 2D table, and manipulates cards, dice, cubes, meeples, and tokens in real time while talking on a separate video or phone call. Think Screentop or PlayingCards.io, but purpose-built: each exercise brings its own components, zones, seats, and macro buttons, so a facilitator presses “Deal” or “Reset” and the table arranges itself for that exercise.

The first two exercises are “Value Cards Trading” and “Democracy Simulation.” The platform must make a third exercise cheap to add.

Facilitators—teachers, community organisers, and workshop leads—run groups of 4–30 participants on laptops and tablets. There is no sign-in: a room is a URL with a code, and a participant enters a display name to join the table.

The experience is real time but unhurried. Dragging must feel immediate to the person doing it; everyone else may see it 100 ms later. This is not a twitch game. Never trade correctness or clarity for latency below that threshold.

The voice and feel should be academic in the good sense: an atmosphere of exploration and learning, and of Socratic exchange where disagreement is expected and safe. It should feel like a seminar room and scholarly edition, not a game show or corporate SaaS. There are no points, streaks, confetti, badges, or leaderboards. Nobody wins an ethics exercise.

## Stack

- Python 3.12
- FastAPI on Uvicorn
- SQLAlchemy 2.0 with Postgres in production and SQLite locally
- Jinja2 templates for all non-table pages
- Pydantic v2 for every boundary
- WebSockets for the table
- pytest and Playwright for tests
- TypeScript compiled by Vite for the table client only
- uv for dependency management
- Ruff and mypy in strict mode

Do not substitute the stack.

## Folder map

- `sandbox/model/` — pure tabletop domain: pieces, zones, and operations; no I/O
- `sandbox/games/` — exercise definitions and their escape-hatch code
- `sandbox/web/` — FastAPI application, routes, and WebSocket hub
- `sandbox/web/templates/` — Jinja templates
- `sandbox/db/` — SQLAlchemy models and migrations
- `client/` — TypeScript table client built by Vite
- `static/` — compiled client output, CSS, and fonts
- `tests/` — automated tests

## The one architectural rule

Python is authoritative for all state and all rules. The TypeScript table client renders what Python sends and reports what the human did. It holds no rules, knows nothing about deck contents, and is never sent the face of a card its viewer is not entitled to see. If a rule appears in TypeScript, that is a bug.

## Rules of engagement

- Every change must keep Ruff, mypy strict, and pytest green before it is called done.
- No exercise-specific logic may enter `sandbox/model/` or `sandbox/web/`.
- Every new dependency must be justified in one line in this file.
- Commits must stay scoped to one prompt.

## Dependency justifications

- FastAPI provides the required typed ASGI web framework and WebSocket support.
- Uvicorn provides the required ASGI development and production server.
- Jinja2 renders the required non-table HTML pages.
- SQLAlchemy provides the required database toolkit without adding database behavior yet.
- Pydantic validates every external boundary and is also FastAPI’s data-contract layer.
- Hatchling makes the Python package and `uv run dev` entry point installable by uv.
- Ruff provides the required Python linting and formatting checks.
- mypy provides the required strict static type checking.
- pytest provides the required Python test runner.
- HTTPX powers FastAPI’s in-process test client.
- Vite compiles and watches the TypeScript table client.
- TypeScript provides static typing for the table client.
- Playwright provides the required browser-level test runner.
