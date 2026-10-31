# Ethics Sandbox

## What it is

The Ethics Sandbox is a virtual tabletop for structured exercises that teach ethics and practice civil discourse skills. A small group joins a room by link, sits at a shared 2D table, and manipulates cards, dice, cubes, meeples, and tokens in real time while talking on a separate video or phone call. Think Screentop or PlayingCards.io, but purpose-built: each exercise brings its own components, zones, seats, and macro buttons, so a facilitator presses “Deal” or “Reset” and the table arranges itself for that exercise.

Exercises are designed by the R&D Studio at the Edmond & Lily Safra Center for Ethics, Harvard University. This attribution belongs on the public landing page's lede (`content/site/site_copy.csv`, key `lede`) and should not be dropped by later copy changes.

The Center's seal is used as the site icon (`static/icons/`) and, in white, on every card back. The brand style guide requires approval from the Center's communications and events team for any use of the logo; the author confirmed on 2026-10-15 that this use is approved. Any new use of the seal or logo needs its own approval. Colours follow the Center's brand style guide, with a pure-white page instead of its off-white.

The first two exercises are “Value Cards Trading” and “Democracy Simulation.” The platform must make a third exercise cheap to add.

Facilitators—teachers, community organisers, and workshop leads—run groups on laptops and tablets. There is no sign-in: a room is a URL with a code, and a participant enters a display name to join the table.

## Rooms and activities

A room is an open sandbox, not one exercise. Up to 20 people join it and use the table however they please: the free table, the value cards, dice, tokens and other loose pieces. No activity is built into a room. An activity is a guided exercise started inside a room: someone presses "Start the <activity>", a sign-up opens for the activity's players (the facilitator may choose them instead), and the activity lays out its own zones for those seats and guides them through its steps. Everyone else keeps using the sandbox, and several activities, or several groups doing the same one, can run in a room at once. An activity's `players: {min, max}` is how many people it takes (three for Value Cards Trading), never the room's capacity.

The facilitator is optional, an admin seat. Nobody is the facilitator by default, the room's creator included. Any participant may take the seat with a "Become facilitator" button, or choose it when joining; only one person holds it, and nothing in any activity requires it.

The experience is real time but unhurried. Dragging must feel immediate to the person doing it; everyone else may see it 100 ms later. This is not a twitch game. Never trade correctness or clarity for latency below that threshold.

The voice and feel should be academic in the good sense: an atmosphere of exploration and learning, and of Socratic exchange where disagreement is expected and safe. It should feel like a seminar room, not a game show or corporate SaaS. There are no points, streaks, confetti, badges, or leaderboards. Nobody wins an ethics exercise. Avoid framing this as a “scholarly edition” or otherwise gilding the tone - keep the register plain and direct.

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
- `sandbox/content_loading.py` — reads the CSV files under `content/` into plain rows
- `sandbox/cli.py` — the `sandbox` command (`uv run sandbox validate-games`)
- `content/` — editorial text as CSV, edited as a spreadsheet; see `content/README.md`
- `client/` — TypeScript table client built by Vite
- `static/` — compiled client output, CSS, and fonts
- `tests/` — automated tests
- `docs/BUILD-PLAN.md` — the build plan, and where the build stands
- `.github/workflows/ci.yml` — CI: Ruff (lint and format), mypy, pytest and the Playwright suite on every pull request and every push to `main`

## Identity without sign-in

A room is a URL with a code; a participant is a signed, http-only cookie holding a
random id, issued on first visit and long-lived, plus whatever display name they
typed when joining that room. That is the whole identity system: no email, no
password, no account, no third-party auth. The same browser returning to the same
room reclaims its seat and its hand because it still carries that cookie. No later
prompt may add a login.

## The one architectural rule

Python is authoritative for all state and all rules. The TypeScript table client renders what Python sends and reports what the human did. It holds no rules, knows nothing about deck contents, and is never sent the face of a card its viewer is not entitled to see. If a rule appears in TypeScript, that is a bug.

## The table client

`client/src/` is the only TypeScript in the project. Vite compiles it to
`static/table/table.js`. It renders what Python sends and reports what the
person did: no rule, no deck, and no face it was not given.

- `protocol.ts` — the wire, mirroring `sandbox/web/live.py`
- `model.ts` — the client's copy of the projected table, and patch folding
- `viewport.ts`, `viewport-input.ts` — pan and zoom arithmetic, and the
  gestures that drive it
- `geometry.ts` — reading the zone outlines the server sends
- `piece-node.ts` — one piece as a DOM element, with its own interpolation
- `table.ts` — the reconcile pass that owns the DOM
- `ink.ts` — the one canvas: ink, pointer pings, other people's cursors
- `connection.ts` — the live socket, with reconnect and replay-from-seq
- `recording.ts`, `fake-server.ts` — a recorded session behind the same
  `ServerLink`, so rendering is built and tested with no backend running
- `perf.ts` — frame measurement
- `interaction.ts` — pointer, touch and keyboard gestures, turned into intents
- `intents.ts` — sending intents and matching each `ack` or `reject` to it
- `menu.ts` — the context menu, whose contents the server supplies
- `reveal.ts` — reveals in progress, and a close look at your own card
- `activities.ts` — the toolbar's activities: what can be started, who has
  signed up, and the buttons that act on one
- `announcer.ts` — the live region that says what happened, in words

Pieces are DOM elements positioned with `translate3d` inside a single
transformed world layer, so card text is real text at any zoom. Rendering
reconciles from state, never from events: a message folds into the model and
records what changed, and one animation frame later only those nodes are
rewritten. Z-order is the model's — the zone's place in the server's list,
then the piece's `z` within that zone — and never DOM insertion order.
Another person's piece interpolates over 120 ms; the piece under your own
hand never does. Your own private zone is drawn in a hand tray outside the
world transform, so it stays put when the table moves.

`/table-preview` replays the recorded session with no room behind it, and
`?pieces=300&measure=1` is the frame-rate harness.

### Interaction

Every gesture is shown at once and proposed as an intent. The local result
is an override laid over the model on the renderer, never a change to the
model itself. The server answers every intent exactly once: `ack` (sent
after its patches, so the truth has already arrived) or `reject` with a
sentence. On `ack` the override is dropped; on `reject` it is dropped with
a visible rollback (the piece glides back and is marked) and the sentence
is shown in a toast. An intent with no answer within eight seconds is
treated as refused. Each intent's `client_id` doubles as its `op_id`, so a
repeat is applied once.

The client never decides legality. Where a piece was let go - over a zone,
over another piece, over the hand tray - is input; it becomes
`move_to_zone`, `stack_onto` or a plain `move`, and the server judges it.
The context menu is a `menu_request` answered by a `menu` message built by
`sandbox/model/actions.py`, which offers every plausible operation and
keeps those whose own `validate` accepts them. Faces a patch newly entitles
a viewer to travel with that patch as `components`, to that viewer only.

Reveals are read from state (`revealed_to`, `revealed_by`), not from
events, so a reconnect sees exactly what is being shown now. Only someone
whose zone lets them see a face may show it (being shown a card does not
count), only they or the facilitator may put it away, and it is put away
when they leave the table. Who is showing what to whom is public; the face
is not.

Keyboard: Tab reaches every piece; arrow keys move by a 20-unit step (Shift
for five); Enter turns over; R and Shift-R rotate; M, the context-menu key
or Shift-F10 open the menu; P points; Escape clears. With nothing focused,
R and Enter act on the selection.

### Measured frame rate

300 pieces on screen, one of them being dragged: **59 fps**, median frame
16.7 ms, 95th-percentile frame 16.8 ms. Measured with
`/table-preview?pieces=300&measure=1` at 1440×900 in headless Chromium,
three runs, timing the drag rather than the first paint. First paint of a
300-piece table costs 80–180 ms. At 600 pieces it holds 50–59 fps.

Two things bought that number and should not be handed back. Placed pieces
carry no CSS transition on `transform`: the interpolation *is* the
animation, and a transition on top of it is two animations fighting over one
property. And `will-change: transform` is set only on the piece actually
being held, not on all of them, because a compositing layer per piece costs
more than it saves. Per-piece shadows were measured at this size and cost
nothing, so they stay: the instruction is to spend the shadows before the
typography, and it has not come to that.

## Game definitions

An activity's table is data. A game (an activity) is a directory under `sandbox/games/`
holding a `game.yaml`, an `__init__.py`, and optionally a `rules.py` for
what the YAML cannot say. No exercise has one yet. The worked example is
Two Doors, a test fixture in `tests/games/two_doors/` whose CSV files are in
`tests/games/content/exercises/two-doors/`: read it alongside this section.
It is not part of the product; the app loads it only when
`SANDBOX_EXTRA_GAMES` names `tests/games`, as pytest and the Playwright
server do.

`game.yaml` has these sections, checked by `sandbox/games/definition.py`:

- `meta` — `slug`, `title`, `players: {min, max}` (how many people the activity takes; the room's cap is separate),
  `duration_minutes`, `facilitator` (required, recommended or optional),
  and `listed`. A listed game's site copy stays in
  `content/site/exercises.csv`, and its title there must match.
- `components` — `decks`, each the rows of a CSV under `content/` (`key`
  names the unique column, `title`/`body`/`folio` the columns on the face,
  `image` the column naming a file in that folder's `images/`), and
  `pieces`: dice with `faces`, tokens, cubes, meeples, notes.
- `seats` — `labels`, given in the order seats are taken; past the end,
  "Seat N". Seats are created as people sit down.
- `zones` — `rect: [x, y, width, height]`, `kind`, `visibility`, `layout`,
  optional `capacity`. `per_seat: true` gives every seat its own copy,
  `<id>-<seat id>`, owned by that seat and moved by `step: [dx, dy]` per
  seat. A `private_to_owner` zone must be per-seat.
- `setup` — steps that build the activity's starting zones and pieces when it is started in a room.
- `macros` — buttons: `id`, `who` (facilitator or anyone), and either
  `steps` or `python: <function>`. Every game has `setup`, `deal`,
  `reset`, `shuffle`, `collect` and `clear_ink`.
- `buttons` — `source:` a CSV saying what each macro's button says, one
  row per macro: `id`, `label`, `hint`, `confirm` (asked first; give one to
  anything destructive) and `announce` (`{name}` and `{label}`).
- `prompts` — `source:` a CSV with `id` and `text` columns.

Steps are `{op: ..., ...}`: `setup` (run the setup steps here),
`spawn_deck`, `spawn`, `shuffle`, `deal` and `draw` (`from`, `to`,
`count`, `face_up`), `collect` (`to`, optional `kinds`, `from`,
`face_up`), `flip`, `reset_table`, `reset_zone`, `clear_ink`. Naming a
per-seat zone means every seat's copy, in seat order. A card dealt or
drawn into its owner's private hand lands face up, so its owner can read
it; anywhere else it stays as it came off the pile. `face_up` in the step
overrides either.

`sandbox/games/engine.py` turns a macro, a new seat, or a new table into
one `Transaction` of concrete operations, trying each against a copy of the
table as it builds. The transaction applies whole or not at all, is logged
as one event with every step in it, is snapshotted, and is announced to the
table. A refusal is the model's own sentence. Spawned pieces get random
ids, and a hidden deck is shuffled as it is made, because an id that
follows a card is a way to read it.

### The escape hatch

`rules.py` registers functions with `sandbox.games.hatch`:

```python
from sandbox.games.hatch import GameContext, MacroRefused, hook, macro
from sandbox.model import Flip, MoveToZone, Operation, Table


@macro("reveal")  # game.yaml: {id: reveal, ..., python: reveal}
def reveal(table: Table, context: GameContext) -> list[Operation]:
    if table.pieces_in_zone("doors"):
        raise MacroRefused("The doors already hold cards. Collect them first.")
    operations: list[Operation] = []
    for seat in context.seats:  # seat order
        hand = table.pieces_in_zone(context.zone("hand", seat))
        if not hand:
            raise MacroRefused(f"{table.seats[seat].label} has no card. Deal first.")
        operations += [
            MoveToZone(piece_id=hand[-1].id, zone_id="doors"),
            Flip(piece_id=hand[-1].id, face_up=True),
        ]
    return operations
```

- `@macro(id)` is the body of the macro whose YAML says `python: id`.
- `@hook("after_setup")`, `@hook("before_macro")` (`context.macro_id`) and
  `@hook("seat_change")` (`context.seat_id`; fires when a seat is added)
  run inside the same transaction as what caused them.
- Each receives a copy of the table and a `GameContext` (`actor_seat`,
  `seats`, `zone(id, seat)`, `seat_zones(id)`) and returns operations. No
  I/O, no global randomness, and no mutating the table: return a
  `Shuffle` or a `Roll` instead. `MacroRefused(sentence)` refuses the
  whole macro with that sentence.
- Test them as plain functions; `tests/games/hooked/` exercises every hook.

`uv run sandbox validate-games` loads every definition, checks every name
it uses, and plays every macro at both ends of the player range; pytest
runs the same check. `/games/{slug}/preview` draws a game's table after
setup from the spectator projection, and an exercise page shows it once
the exercise has a definition. `/start?game={slug}` starts an unlisted
game. Definitions and content hot-reload under `uv run dev`.

### Who may move what

The facilitator may take any piece from anywhere: a locked one, one
someone else is holding mid-drag, one in someone's hand. A participant may
not touch a locked piece, a piece someone else is holding, or a piece in
another seat's private zone; they may give a piece to someone's hand, but
not take one out of it. Only the facilitator may clear a zone, despawn a
piece or reset the table. When the facilitator takes a piece out of
someone's drag, that person's drag so far is logged first, and what they
send for the piece afterwards is refused until they pick it up again.

A rolled die's face (`value` on the wire) is sent only to viewers who may
see the die's face, like its `component_id`. When the last person leaves a
live room, its table is saved as it was left. Who sits where belongs to the
room service: callers of `rooms.claim_seat`, `release_seat`,
`make_observer` and `remove_participant` call `hub.seats_changed(code)`
after committing, and a live room's snapshots never overwrite it.

## Rules of engagement

- Every change must keep Ruff, mypy strict, and pytest green before it is called done.
- No exercise-specific logic may enter `sandbox/model/` or `sandbox/web/`.
- Every new dependency must be justified in one line in this file.
- Commits must stay scoped to one prompt.
- Name each branch for the work it contains (for example `claude/mac-lan-deploy-script`), not with a generated name; this is explicit permission to push to that branch instead of an assigned one.
- Push every commit as soon as it is made, and keep every pushed branch in an open pull request against `main`. Open it with the first push, following `.github/pull_request_template.md` (summary, questions for the author, follow-up needed to activate the work, checks); when later commits change the picture, update its description. Keep the template consistent with the one in HolyTispoon/HEARsay-Mysteries-Commons-Comma: the shared sections are word for word the same, and this repo adds only the build-plan pointer and the Checks list.
- Watch every pull request you open or push to, from the first push until it
  is merged or closed: subscribe to its activity (in a Claude Code session,
  `subscribe_pr_activity`) and act on what arrives - fix failing checks and
  merge conflicts, and answer or address review comments. If the session
  cannot subscribe, say so in the pull request rather than leaving it
  unwatched.
- Every pull request description has a "Questions for the author" section
  (see `.github/pull_request_template.md`): every open question, every
  assumption made where the request, the plan or the content was unclear,
  and anything the author should double-check, numbered. If there is
  genuinely nothing, it says "None" and why.
- Claim a build-plan step before starting it, with
  `scripts/claim-step.sh <number>` (see "Claiming a step" in
  `docs/BUILD-PLAN.md`), and open a draft pull request for its branch at
  once. A step whose branch already exists on GitHub, or that has an open
  pull request, is taken: do not work on it, even if the status table on
  `main` says otherwise. Work on a claimed step goes on the branch named for
  it in the status table, which takes the place of a descriptive name.
- `docs/BUILD-PLAN.md` is the build plan and its status. A pull request
  that completes or advances a step updates the status in the same pull
  request. Where the plan and this file disagree, this file wins.

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
- Hypothesis provides property-based tests for `sandbox/model/`, required to check the security and integrity invariants of `project()` and the operations against far more tables and sequences than hand-written examples could cover.
- Alembic manages the SQLAlchemy schema as versioned migrations, so production (Postgres) and local development (SQLite) are always brought to the same shape deliberately, never by `create_all` drift.
- python-multipart is required by Starlette to parse the HTML form submissions on `/start` and `/join`.
- pytest-asyncio runs the realtime tests, which must await the room task itself rather than a synchronous stand-in for it.
- PyYAML reads each exercise's `game.yaml`, the definition format the build plan specifies.
- types-PyYAML gives mypy strict the types for PyYAML.
- anyio (already installed by Starlette, now imported directly) lets the `/join` route, which runs on a worker thread, tell a live room about a new seat before it answers.

## Design tokens

All colour literals live in `static/css/tokens.css`. Components consume only the
custom properties below. The semantic colours are reserved for game state:
assent/agreed, tension/contested, and caution/time short.

- Surfaces: `--surface-page`, `--surface-raised`, `--surface-sunken`,
  `--surface-border`, `--surface-border-strong`
- Table: `--table-felt`, `--table-felt-edge`, `--table-zone-outline`,
  `--table-zone-private`, `--table-drop-target`
- Card back: `--card-back`, `--card-back-edge`, `--card-back-ink` (crimson in
  both themes, so a face-down card looks the same in light and dark)
- Text: `--text-primary`, `--text-secondary`, `--text-muted`, `--text-inverse`,
  `--text-on-felt`
- Accent: `--accent-rubric`, `--accent-rubric-soft`
- Semantic: `--semantic-assent`, `--semantic-tension`, `--semantic-caution`
- Seats: `--seat-1`, `--seat-2`, `--seat-3`, `--seat-4`, `--seat-5`,
  `--seat-6`, `--seat-ink`
- Supporting colour: `--overlay`, `--shadow-color`, `--shadow-color-strong`,
  `--transparent`
- Type: `--font-reading`, `--font-ui`, `--font-mono`, `--text-xs`, `--text-sm`,
  `--text-md`, `--text-lg`, `--text-xl`, `--text-2xl`, `--text-3xl`,
  `--leading-tight`, `--leading-reading`, `--tracking-label`,
  `--measure-reading`
- Space: `--space-1` through `--space-8`
- Shape and depth: `--radius-sm`, `--radius-md`, `--radius-lg`,
  `--line-hairline`, `--line-strong`, `--shadow-raised`, `--shadow-piece`,
  `--focus-ring`
