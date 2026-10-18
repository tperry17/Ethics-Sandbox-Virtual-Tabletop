# The Ethics Sandbox — Build Plan

This file is the build plan the project is being built from: a series of
prompts, run in order, one branch and one pull request each. The top of the
file says where the build stands; the prompts themselves follow, as written.

CLAUDE.md is the project constitution and wins wherever it and this plan
disagree. Several things have changed since the plan was written (listed
below); where a prompt still says otherwise, follow CLAUDE.md.

Every pull request that completes or advances a step updates the status
table below in the same pull request.

## Where we are

Prompts 1–8 are done. Prompt 9, game definitions and macro buttons, is
claimed and in review in PR #9. Prompts 10 and 11 need written rules from
the author before they can run (see "Waiting on the author"). Prompts 12–16
are unclaimed, but Prompt 12 says it is built after the games, so it is
best left until 10 and 11 can run.

Before starting a step, claim it (see "Claiming a step"). A claimed step
shows "Claimed" in this table on `main`.

| # | Step | Status | Branch | Commit or PR |
|---|------|--------|--------|--------------|
| 1 | Repo scaffold and project constitution | Done | | `2006c3c` |
| 2 | Design system | Done; palette revised to the Center's brand guide | | `5834435`, then the `claude/center-brand-palette` PR |
| 3 | The public site | Done, with gaps (below) | | `5fc34dd`, then `d491312`, `108a5cb` |
| 4 | The tabletop model | Done | | `47c6c80` |
| 5 | Rooms, identity and persistence | Done, with gaps (below) | | `08cfbe8` |
| 6 | The realtime layer | Done | | `d852f75` |
| 7 | The table client — rendering | Done | | `9c86f37` |
| 8 | The table client — interaction | Done | | `d8c383d` (PR #1) |
| 9 | Game definitions and macro buttons | Claimed; in review | `claude/game-definitions` | PR #9 |
| 10 | Value Cards Trading | Waiting on the author's rules | `claude/step-10-value-cards-trading` | |
| 11 | Democracy Simulation | Waiting on the author's rules | `claude/step-11-democracy-simulation` | |
| 12 | Facilitator controls and the shared view | Not started | `claude/step-12-facilitator-controls` | |
| 13 | Reflection, debrief and the playtest record | Not started | `claude/step-13-reflection-and-debrief` | |
| 14 | Access, tablets and resilience | Not started | `claude/step-14-access-and-resilience` | |
| 15 | Tests | Not started | `claude/step-15-tests` | |
| 16 | Launch pass | Not started; deployment target has changed (below) | `claude/step-16-launch-pass` | |

### Claiming a step

A step is claimed by the existence of its branch on GitHub. Each unfinished
step has one fixed branch name in the table above, so two people (or two
Claude sessions) starting the same step reach for the same branch, and
GitHub accepts only the first push to it.

To claim a step, run `scripts/claim-step.sh <number>` from a clean checkout.
It:

1. refuses if the step is Done, waiting on the author, or already Claimed
   on `main`;
2. refuses if the step's branch already exists on GitHub - someone has it;
3. creates the branch from `origin/main`, marks the step "Claimed" in this
   table, commits, and pushes without force. If someone else pushed the
   branch first, the push is rejected and the claim fails;
4. marks the step "Claimed" in this table on `main` too, with a one-line
   commit pushed straight to `main`, so anyone reading the table there sees
   the claim. If that push keeps failing, the claim still holds and the
   script says to mark the row by hand.

Then open a draft pull request for the branch at once, titled
`Prompt <number>: <step>`, so the claim is visible to anyone looking at
the pull requests. Do the work on that branch only.

If the claim fails, the step is taken: do not work on it, and do not push
to its branch. To give a claim up, close its pull request and delete its
branch; the step is then free again.

Without the script, the check is the same by hand: look at the step's row
on `main`, for the step's branch (`git ls-remote --heads origin <branch>`)
and for an open pull request naming the step. If any of them shows a claim,
the step is taken.

Work outside the numbered prompts, already merged:

- `d491312` — editorial text moved out of Python into CSV files under
  `content/`, edited as a spreadsheet.
- `108a5cb` — landing page shows exercises before principles; new lede with
  the R&D Studio attribution.
- `a32c5d3` — an `image` column in `cards.csv` and `roles.csv`, so a card
  or role can be an uploaded image.
- `880b3d1` (PR #2) — `scripts/deploy.sh` serves the tabletop from a Mac on
  the local network.
- `c88eb82` (PR #3) — descriptive branch names and a pull request for every
  pushed branch.

## Gaps in completed steps

Checked against the code on `main`; none of these has been fixed yet.

- **Prompt 3.** The `/exercises`, `/principles` and `/about` routes do not
  exist; the site has `/` and `/exercises/{slug}` only. No page sets OG
  meta tags. The exercise page's "preview image" is an HTML mock-up built
  from `content/site/exercise_preview_*.csv`, not an image of a real table.
- **Prompt 5.** Rooms do not go dormant after 12 idle hours and are not
  purged after 30 days, and the UI does not announce either.
- **Prompt 2.** `/styleguide` still describes the design as a "scholarly
  edition", which CLAUDE.md now rules out. Being removed in a separate PR.
- **No CI.** There is no `.github/workflows/`. Prompt 9 asks for
  `validate-games` to fail CI, and Prompt 15 wires the suite into CI.

## Changes since the plan was written

Where these conflict with a prompt below, these win.

- **Voice.** Prompts 1 and 2 describe the look and voice as a "scholarly
  edition". CLAUDE.md now says to avoid that framing and keep the register
  plain and direct.
- **Editorial text lives in CSV.** All site copy, and each exercise's deck
  or roles, is in `content/` as CSV (see `content/README.md`). A prompt
  that says to write copy or decks in Python, templates or YAML should put
  the editable text in CSV instead.
- **Images as card faces.** A card or role may be an uploaded image, named
  in the `image` column of its CSV. Prompts 9–11 already say so.
- **Deployment.** Section 0 and Prompt 16 say Fly.io or Render. The current
  way to run a session is `scripts/deploy.sh` on a Mac on the local
  network. Prompt 16's hosting choice is open (see below).
- **Call.** Section 0 says Zoom; CLAUDE.md says a separate video or phone
  call. Nothing depends on which.
- **Branches and pull requests.** CLAUDE.md now requires a descriptive
  branch name, a pull request for every pushed branch, and a "Questions for
  the author" section in every pull request description.

## Waiting on the author

- **Prompt 10:** the rules of the trading exercise (the `<<<PASTE …>>>`
  block), and a complete `content/exercises/value-cards-trading/cards.csv`.
  It has two rows today.
- **Prompt 11:** the rest of the Democracy Simulation rules, and a complete
  `content/exercises/democracy-simulation/roles.csv`. It has two rows today.
- **Prompt 16:** whether to deploy to a host (Fly.io, Render or other) or
  keep serving from a Mac on the local network.

---

## The plan as written

A sequence of prompts for a coding agent (Claude Code or Cursor) working in a real repo. Run them **in order**, one session and one commit each. Prompt 1 writes the `CLAUDE.md` that every later prompt depends on, and Prompt 4 defines the tabletop model that Prompts 5 through 16 all sit on — those two are the ones not to rush.

Three prompts contain a `<<<PASTE …>>>` marker. Replace it with your own written material before sending; each of those prompts lists exactly what your material needs to cover.

---

## 0. What is being built, and in what

The Ethics Sandbox is a **virtual tabletop** — a shared 2D surface where a group manipulates cards, dice, cubes, meeples and tokens in real time while talking to each other on a separate Zoom or phone call. It is closest in spirit to Screentop or PlayingCards.io, but tailored: each exercise brings its own components, zones, seats and macro buttons, so a facilitator can press **Deal**, **Set up** or **Reset** and have the table arrange itself correctly for that exercise.

No sign-in, ever. A room is a URL with a code in it; you type a name and you are at the table.

**Python owns everything that counts.** The tabletop model, the visibility rules, the decks and shuffles, the macros, the exercise definitions, persistence, and the event log are all Python. The public site is server-rendered from Jinja templates. The single exception is the table surface itself, which must run in the browser because dragging a card cannot wait on a server round trip.

**FastAPI + Uvicorn · SQLAlchemy + Postgres (SQLite for local dev) · Jinja2 · WebSockets · Pydantic · pytest + Playwright · TypeScript + Vite for the table client only · deployed on Fly.io or Render.**

The table client is a renderer and an input translator. It contains no rules — no notion of what a legal move is, no knowledge of what is in a deck, no ability to see a card it has not been told the face of. Pieces are DOM elements positioned with CSS transforms so card text stays crisp and readable; one canvas layer sits on top for ink and pointers. No UI framework. Enforce this boundary in review: if a rule appears in TypeScript, it is a bug.

---

## 1. Repo scaffold and project constitution

**Status: Done.**

Sets the ground rules once so you never re-explain the project. The `CLAUDE.md` it writes is read automatically by every later session.

```text
Start a new project called the Ethics Sandbox.

WHAT IT IS
A virtual tabletop for structured exercises about values, ethics and
democratic decision-making. A small group joins a room by link, sits at a
shared 2D table, and manipulates cards, dice, cubes, meeples and tokens in
real time while talking on a separate video or phone call. Think Screentop
or PlayingCards.io, but purpose-built: each exercise brings its own
components, zones, seats and macro buttons, so a facilitator presses "Deal"
or "Reset" and the table arranges itself for that exercise.

The first two exercises are "Value Cards Trading" and "Democracy
Simulation". The platform must make a third exercise cheap to add.

WHO USES IT
Facilitators (teachers, community organisers, workshop leads) running 4-30
people, plus participants on laptops and tablets. No sign-in, ever: a room
is a URL with a code, you type a display name, you are at the table.

PACE
Real time but unhurried. Dragging must feel immediate to the person doing
it; everyone else may see it 100ms later. This is not a twitch game. Never
trade correctness or clarity for latency below that threshold.

VOICE AND FEEL
Academic in the good sense: an atmosphere of exploration and learning,
Socratic exchange, where disagreement is expected and safe. Seminar room
and scholarly edition, not gameshow and not corporate SaaS. No points, no
streaks, no confetti, no badges, no leaderboard. Nobody wins an ethics
exercise.

STACK (do not substitute)
Python 3.12. FastAPI on Uvicorn. SQLAlchemy 2.0 with Postgres in
production and SQLite locally. Jinja2 templates for all non-table pages.
Pydantic v2 for every boundary. WebSockets for the table. pytest and
Playwright for tests. TypeScript compiled by Vite for the table client
only. uv for dependency management. Ruff and mypy strict.

THE ONE ARCHITECTURAL RULE
Python is authoritative for all state and all rules. The TypeScript table
client renders what Python sends and reports what the human did. It holds
no rules, knows nothing about deck contents, and is never sent the face of
a card its viewer is not entitled to see. If a rule appears in TypeScript,
that is a bug.

DO NOW
1. Scaffold with uv. Configure Ruff, mypy strict, pytest.
2. Create this structure with a one-line README in each folder:
     sandbox/model/      pure tabletop domain: pieces, zones, ops, no I/O
     sandbox/games/      exercise definitions and their escape-hatch code
     sandbox/web/        FastAPI app, routes, websocket hub
     sandbox/web/templates/   Jinja
     sandbox/db/         SQLAlchemy models and migrations
     client/             TypeScript table client, built by Vite
     static/             compiled client output, css, fonts
     tests/
3. A running FastAPI app serving one Jinja page, one passing pytest, one
   passing Playwright test, and a Vite build wired so `uv run dev` starts
   the server and the client watcher together.
4. Write CLAUDE.md containing the description above, the stack, the folder
   map, the one architectural rule, and a "Rules of engagement" section
   requiring that every change keep `ruff`, `mypy`, and `pytest` green
   before being called done; that no exercise-specific logic enters
   sandbox/model/ or sandbox/web/; that new dependencies are justified in
   one line in CLAUDE.md; and that commits stay scoped to one prompt.
5. Commit.

DO NOT yet: build the table, add the database, or design anything.
```

---

## 2. Design system

**Status: Done.**

The colour values were later revised to the Center's brand style guide: a
white page instead of cool paper, Harvard crimson (`#a41034`) as the accent,
and the guide's dark and light blues for ink and the table. The token names,
the dark-mode structure and the seat tints are unchanged. The prompt below is
kept as it was given.

Do this before any real screen exists, or you will spend the build fighting inconsistent spacing. It covers both the site and the table felt, which need to feel like one place.

```text
Read CLAUDE.md. Build the Ethics Sandbox design system as plain CSS with
custom properties in static/css/. No feature work, no framework.

DIRECTION
A scholarly edition rendered for screen. Cool paper rather than warm cream.
Ink-black text. One accent, a rubric red, used the way early printers used
it: section marks, rules, the active state, the number on a phase. Nothing
else is coloured for decoration. The table surface is a quieter, deeper
version of the same world - a desk, not a casino baize. Generous margins,
a real type scale, quiet surfaces.

TOKENS
Define under :root, redefine for dark mode under both
`@media (prefers-color-scheme: dark)` guarded as
`:root:not([data-theme="light"])` and `:root[data-theme="dark"]`.
Never write a raw hex outside the token file.
  surfaces   page, raised, sunken, border, border-strong
  table      felt, felt-edge, zone-outline, zone-private, drop-target
  text       primary, secondary, muted, inverse
  accent     rubric, rubric-soft
  semantic   assent, tension, caution - used ONLY for game state
             (agreed / contested / time short), never as decoration
  seats      six deterministic seat tints, distinguishable in both themes
             and under the two most common colour-vision deficiencies
Neutrals carry a slight cool bias, not pure grey.

TYPE - three roles, self-hosted from Google Fonts as woff2 in static/fonts:
  Spectral        headings and all reading prose, including card faces
  IBM Plex Sans   UI: buttons, labels, toolbars, form fields
  IBM Plex Mono   room codes, timers, counts, dice values, tabular numbers
Modular scale near 1.25 as tokens. Reading measure caps at 68 characters.
Headings get text-wrap: balance. Uppercase labels get letter spacing.
Columns of digits get tabular-nums.

COMPONENTS as CSS classes plus Jinja macros in web/templates/_ui.html:
Button (primary / secondary / quiet / destructive, three sizes), Card,
Field with real label and error text, Dialog, Tag, Callout, SectionRule,
Timer, RoomCode, Avatar (initials, seat tint), EmptyState, Toolbar,
Toast.

TABLETOP PIECE STYLES, as CSS only - no behaviour yet:
  .piece--card   a physical object with weight: crisp face at any zoom,
                 a distinct back, a rest state and a lifted state,
                 a held-by-someone-else state showing whose seat tint
  .piece--die .piece--cube .piece--meeple .piece--token .piece--note
  .zone          outline, label, and a clear drop-target state
  .zone--private visibly, obviously not public
Cards must remain readable at 60% zoom. Test this.

RULES
Visible focus ring on everything interactive. All motion behind
prefers-reduced-motion. No component sets a colour literal. Spacing from
flex/grid gap, not stacked margins.

Finish with a /styleguide route rendering every token, component and piece
style in every state on one page. Record the token names in CLAUDE.md.
Commit.
```

---

## 3. The public site

**Status: Done, with gaps (see top).**

The part a stranger sees. Its job is to make a facilitator think "I could run this on Thursday."

```text
Read CLAUDE.md and /styleguide. Build the public, non-table site as
server-rendered Jinja using only existing tokens and components.

ROUTES
/                  Landing
/exercises         The library
/exercises/{slug}  One exercise in detail
/principles        House rules for discourse
/about             What this is and who made it

LANDING
Open with the premise, not a slogan: one sentence on what the Ethics
Sandbox is, one on what a session is actually like - a group on a call
together, moving cards on a shared table, arguing - and two actions,
"Start a table" and "See the exercises". Then a short section on the shape
of every exercise here: play, then argue, then look at what you did. Then
the two exercise cards. Then the principles, condensed. No hero image, no
viewport-height opener, no testimonials.

EXERCISE DETAIL - this page decides whether someone runs it, so it carries
  the premise in one paragraph
  group size, running time, whether a facilitator is needed
  what you need alongside it (a video call, roughly this long)
  "What you'll be doing" - the shape of a session in a few lines
  "What tends to come up" - the tensions it reliably surfaces
  facilitator notes in a collapsible panel
  a preview image of the table set up for that exercise
  a "Start a table" action

Drive every page from the exercise definition files, not from hand-written
templates, so a new exercise appears here automatically. Write real copy
for both exercises from the descriptions in CLAUDE.md and mark anything
invented with a TODO comment.

PRINCIPLES
Five to seven short norms for discourse in a session - steelman before you
object, disagree with the position not the person, change your mind out
loud. These are shown again at the table, so keep them in one data file
and render from it.

Responsive to 380px. Semantic landmarks. Metadata and OG tags per route.
Commit.
```

---

## 4. The tabletop model

**Status: Done.**

The heart of the system, and the reason the whole thing is in Python. Pure functions, no database, no web, no async — so it can be tested exhaustively and reasoned about. Spend real time reviewing what comes out of this one.

```text
Read CLAUDE.md. Build the tabletop domain model in sandbox/model/. Pure
Python: no FastAPI import, no SQLAlchemy import, no async, no I/O. Every
function deterministic.

ENTITIES (dataclasses or Pydantic models)
  Piece    id, kind (card|die|cube|meeple|token|note|marker|board),
           component_id (what it is, from the game definition),
           zone_id, x, y, z, rotation, face_up, held_by (seat|None),
           locked, props dict
  Zone     id, kind (table|hand|deck|discard|tray|seat_area|slot),
           label, geometry (rect or polygon), owner_seat (or None),
           visibility, layout (free|stack|fan|grid|spread), capacity
  Seat     id, label, tint_index, participant_id (or None), is_facilitator
  Stroke   id, seat_id, colour, width, points, created_at
  Table    pieces, zones, seats, strokes, rng_state, version

VISIBILITY - the part to get exactly right
  A Zone's visibility is one of:
    public            everyone sees faces of face-up pieces
    private_to_owner  only the owning seat sees faces, others see backs
                      and a count
    facilitator_only  owner and facilitator
    hidden            nobody sees faces; a deck
  project(table, viewer_seat) -> ViewTable returns ONLY what that viewer is
  entitled to know. A face-down card, or a card in someone else's hand, is
  returned with its component_id stripped and a back reference in its
  place. This function is the single security boundary in the product:
  everything sent to a browser goes through it. Test it adversarially.

OPERATIONS - each is a small class with validate() and apply()
  grab, release, move, move_to_zone, flip, rotate, reorder_z
  shuffle(zone), draw(n, from_zone, to_zone), deal(spec)
  roll(piece_or_zone), set_prop, lock, unlock
  group, ungroup
  point(x, y), ink_begin, ink_append, ink_end, erase_ink
  spawn(component_id, zone, count), despawn
  reset_zone, reset_table
  show_to(piece, seats)  - a deliberate reveal to named seats only
  peek(piece)            - the owner looks without revealing; logged
Each takes (table, actor_seat, payload), returns Ok(patches) or
Reject(reason). Reasons are readable sentences a person could be shown.
Nothing mutates the table except apply(). Every apply returns a list of
patches - minimal descriptions of what changed - not a whole new table.

RANDOMNESS
One seeded RNG per table, its state stored on the Table. Shuffles and rolls
draw from it, so any session can be replayed exactly from its event log.
Never call the global random module.

RULES OF THE MODEL
  A piece held by one seat cannot be moved by another.
  A locked piece cannot be moved by anyone but the facilitator.
  Moving a piece into a private zone strips its visibility for others in
  the same operation, never as a separate step.
  Every operation is idempotent by id, so a retried message is harmless.

TESTS - this module gets the most thorough test suite in the repo.
Unit-test every operation including every rejection. Then write
property-based tests with Hypothesis: no sequence of legal operations from
any starting table may ever cause project() to return a component_id to a
seat not entitled to it; no sequence may lose or duplicate a piece; a table
replayed from its event log equals the original.

Commit.
```

---

## 5. Rooms, identity and persistence

**Status: Done, with gaps (see top).**

No sign-in is a feature, not an absence — it needs designing.

```text
Read CLAUDE.md and sandbox/model/. Build persistence and rooms in
sandbox/db/ and sandbox/web/.

IDENTITY WITHOUT SIGN-IN
A signed, http-only cookie holding a random participant id, issued on
first visit and long-lived. That is the whole identity system. A display
name is typed when joining a table and stored against the participant for
that room. The same browser returning to the same room reclaims its seat
and its hand. No email, no password, no account, no third-party auth.
Write this in CLAUDE.md as a product rule so no later prompt adds a login.

SCHEMA (SQLAlchemy + Alembic)
  rooms         id, code (6 chars, unambiguous alphabet), game_slug,
                status (open|paused|closed), config JSON,
                facilitator_participant_id, created_at, last_active_at,
                closed_at
  participants  id, room_id, cookie_id, display_name, seat_id, is_observer,
                connected, last_seen_at
  table_states  room_id, version, snapshot JSON, updated_at
  events        id bigserial, room_id, seq, actor_seat, op_type,
                payload JSON, created_at
  reflections   id, room_id, participant_id, prompt_key, body,
                visibility (private|room), created_at

events is append-only and is the record of what happened - never update or
delete a row in it. table_states is a periodic snapshot so a late joiner
does not replay thousands of events; write one every 200 events and on
every macro.

SERVICES in sandbox/web/rooms.py
  create_room(game_slug, facilitator_name, config)
  join_room(code, display_name)   - assigns a free seat or observer status,
                                    rejects closed rooms, dedupes names,
                                    reattaches a returning cookie
  claim_seat, release_seat, rename, make_observer, remove_participant
  close_room, pause_room
  apply_op(room_id, actor_seat, op)  - the ONLY write path into a table:
                                       validate, apply, persist event,
                                       return patches
Rooms go dormant after 12 hours idle and are purged after 30 days, both
configurable and both announced in the UI.

ROUTES
/start            choose an exercise, name yourself, create a table
/join             enter a code
/t/{code}         the table page shell: header with code and copy button,
                  seat roster, toolbar slot, and the mount point for the
                  table client

Commit.
```

---

## 6. The realtime layer

**Status: Done.**

Small and boring on purpose. This is what makes a session feel alive or feel broken.

```text
Read CLAUDE.md. Build the WebSocket hub in sandbox/web/live.py. Transport
and sync only - no game rules, they live in the model.

PROTOCOL, JSON, Pydantic models for every message in both directions.
  client -> server
    hello {room_code, last_seq}
    intent {client_id, op_type, payload}    - a proposed operation
    cursor {x, y}                           - ephemeral, never persisted
    heartbeat
  server -> client
    snapshot {view_table, seq, seats, you}  - projected for this viewer
    patches {seq, patches[]}                - projected for this viewer
    reject {client_id, reason}              - readable sentence
    presence {seats, cursors}
    notice {level, text}                    - "Ana has left the table"

RULES
  Every outbound message passes through project() for that viewer. There is
  no code path that sends unprojected state. Add a test that asserts it.
  The server assigns the sequence number; clients never do.
  Drag: the client sends move intents at most 20 times a second while
  dragging; the server broadcasts at most 15 times a second, coalescing
  intermediate positions per piece. Only the final position is written to
  the event log - do not log 200 intermediate moves.
  Cursors and pointing go out at 10Hz on a separate ephemeral path and are
  never persisted.
  Soft locks: grab sets held_by. Another seat's move on a held piece is
  rejected with a reason. A hold auto-releases after 10 seconds without an
  update, or immediately on disconnect.
  Reconnect: hello carries last_seq; the server replies with patches since
  that point, or a fresh snapshot if the gap is too large. Never force a
  page reload.
  Backpressure: if a client falls behind by more than 2 seconds of
  messages, drop its queue and send a fresh snapshot.

One asyncio task per room owning that room's state, with intents arriving
on a queue, so operations on a table are serialised and no lock is needed.

Test with pytest-asyncio: ordering, reconnect with a gap, duplicate intent,
rejected intent, a client that stops reading, and two clients grabbing the
same piece in the same tick.

Commit.
```

---

## 7. The table client — rendering

**Status: Done.**

The only TypeScript in the project. Written once, touched rarely.

```text
Read CLAUDE.md. Build the rendering half of the table client in client/.
TypeScript, no UI framework, built by Vite. It holds no rules and no
knowledge the server has not sent it.

STRUCTURE
  A viewport div, transformed for pan and zoom with a single CSS transform
  on an inner world layer. Pieces are DOM elements inside the world layer,
  each positioned with translate3d and rotate, so card text renders as real
  text at any zoom and inherits the design system's typography.
  One canvas element above the world layer for ink strokes and pointers,
  drawn in world coordinates and redrawn on transform change.
  A fixed hand tray along the bottom edge, outside the world transform,
  showing the viewer's private zone in a fan layout.
  A toolbar along the top for macro buttons, which arrive from the server.

RENDERING
  Reconcile from state, not from events: a patch updates the local model,
  then a single requestAnimationFrame pass updates only the DOM nodes whose
  properties changed. Never rebuild the table.
  Remote piece movements interpolate over roughly 120ms so other people's
  hands look smooth rather than teleporting; the local dragger's own piece
  never interpolates.
  Card faces render from the component data the server sent. A piece whose
  face the viewer is not entitled to renders as a back - the client is
  simply never given the face, so there is nothing to leak.
  Z-order comes from the model, not from DOM insertion order.
  Zones render their outline and label, and light up as drop targets.
  Pan with space-drag or middle-drag or two-finger; zoom on wheel and
  pinch, clamped to 40%-250%, zooming toward the pointer. A "fit table"
  control resets it.
  A quiet connection indicator: connected, reconnecting, or offline.

PERFORMANCE TARGET
  300 pieces on screen, dragging one, holds 60fps on a five-year-old
  laptop. Measure it and write the number in CLAUDE.md. If DOM cannot hold
  that, reduce per-piece shadows and filters before considering canvas -
  the text has to stay real.

Build against a fake in-memory server that replays a recorded session, so
rendering can be developed and tested without the backend. Commit.
```

---

## 8. The table client — interaction

**Status: Done.**

Everything a person can do with their hands. This is where the product either feels good or doesn't.

```text
Read CLAUDE.md and the rendering client. Add interaction. Every gesture
sends an intent and waits for the server's answer, while showing the local
result immediately and rolling back visibly if rejected.

POINTER
  Click-drag a piece to move it. Pick up feels like picking up: a small
  lift, a shadow, no delay.
  Click empty table and drag to marquee-select. Selected pieces move,
  flip and rotate together.
  Double-click flips. R rotates 90 degrees, shift-R the other way.
  Drag onto a zone to move it there; the zone shows it will accept.
  Drag a piece onto another to stack them; drag off the top to unstack.
  Right-click or long-press opens a context menu on a piece: flip, rotate,
  send to my hand, show to table, show to one person, move to top or
  bottom, lock, delete. Menu contents come from the server, since what is
  legal depends on rules the client does not know.

HANDS AND REVEALING - the exercise depends on these being exactly right
  The hand tray is private and visibly so. Drag from hand to table to play
  a card; drag from table to tray to take one.
  Hold on a card in your hand to enlarge it for reading; this is a peek,
  visible to no one, but logged.
  "Show to table" reveals a card to everyone for as long as it is held up,
  then returns it - the card is not played, it is shown.
  "Show to..." reveals to named seats only. Everyone else sees that a
  reveal happened and to whom, but not what.
  Any reveal appears to others as an obvious, unmissable event, because
  in these exercises showing a card is a speech act.

POINTING AND INK
  Hold a modifier and click, or press a Point button, to place a transient
  marker with your name and seat tint that fades after three seconds.
  A pen tool draws on the table in your seat tint; strokes are shared,
  persist until erased, and each person can clear their own. The
  facilitator can clear all.

FEEDBACK
  A rejected intent snaps the piece back and shows the server's sentence in
  a quiet toast. Never a raw error code.
  Show, always and unobtrusively, who is holding what.
  Full keyboard alternative for every gesture: tab to a piece, arrow keys
  to move by a grid step, Enter to flip, and a keyboard-reachable context
  menu. Announce piece movements and reveals in a live region.

Commit.
```

---

## 9. Game definitions and macro buttons

**Status: Claimed; in review in PR #9.**

The prompt that makes a third exercise cheap. Data-driven, with a Python escape hatch for mechanics the generic format cannot express.

```text
Read CLAUDE.md and sandbox/model/. Build the game definition system in
sandbox/games/.

A game is a directory containing a YAML definition, optional assets, and an
optional Python module for anything the YAML cannot express.

THE YAML DEFINES
  meta        slug, title, blurb, group size range, duration, whether a
              facilitator is required
  components  reusable definitions: card decks (each card with a front, a
              back, and arbitrary fields available to the templates - a
              front may be an uploaded image instead of a generated one,
              per the `image` column in a deck's content CSV, so read that
              column rather than assuming every card is rendered from
              text), dice with faces, cubes, meeples, tokens, notes, boards
  seats       how many, labels or roles, whether roles are assigned or
              chosen, seat areas on the table
  zones       geometry, kind, visibility, layout, ownership, labels
  setup       the ops that build the starting table
  macros      named buttons: label, who may press them (facilitator or
              anyone), a confirmation prompt if destructive, and either a
              list of ops or the name of a Python function
  prompts     facilitation questions the host can push to every screen

MACROS are the feature that makes this yours rather than a generic table.
At minimum every game gets: Set up, Deal, Reset, Shuffle deck, Collect all
cards, and Clear ink. A macro is a single atomic transaction: it either
applies entirely or not at all, appends one event describing itself, and
announces itself to the table ("Tom dealt 5 cards to everyone").

THE PYTHON ESCAPE HATCH
A game module may register functions decorated with @macro and @hook.
Hooks fire on defined moments (after setup, before a macro, on seat
change) and receive the table plus a typed context, returning ops. They
are pure and testable like everything else in the model. Document the
contract in CLAUDE.md with a worked example.

TOOLING
  `uv run sandbox validate-games` checks every definition against the
  schema, verifies component references, and fails CI on error.
  Definitions hot-reload in development.
  A /games/{slug}/preview page renders the table after setup as a static
  image, used on the exercise pages.

Build a complete reference game, "Two Doors": a small deck, two seats,
private hands, a public table, and three macros (Set up, Deal one each,
Reveal). Keep it in the repo as the worked example, fully tested. Commit.
```

---

## 10. Value Cards Trading

**Status: Waiting on the author's rules.**

The first real exercise. It is a game definition, not new code — if it needs new code, that is a signal the engine is missing something.

```text
Read CLAUDE.md and sandbox/games/. Build the Value Cards Trading exercise
as a game definition.

The card content lives in
content/exercises/value-cards-trading/cards.csv (one row per card: name,
short_definition, fuller_gloss, tension_example, image - `image` names a
file in the sibling images/ folder and is blank for a generated card) -
fill it in completely before running this prompt; read it rather than
asking for the deck to be pasted in. A card with an `image` uses that
image as its face; the text fields still drive the deck list, validation,
and the printable page. The rules of the trading exercise are below. Implement exactly
these. If anything is ambiguous, contradictory or incomplete, STOP and list
the questions rather than guessing. Anything you have to invent, mark with
a TODO comment.

<<<PASTE THE RULES OF THE TRADING EXERCISE HERE - HOW MANY CARDS EACH
PERSON STARTS WITH, WHETHER CARDS ARE DUPLICATED ACROSS HANDS, WHAT A LEGAL
TRADE IS, HOW ONE IS AGREED, WHETHER THERE ARE ROUNDS AND WHAT ENDS ONE>>>

REGARDLESS OF THE RULES, this exercise must:
  - carry each value card's name, a one-sentence definition a 14-year-old
    understands, a fuller gloss, and an example of the value in tension
    with another; card faces must be readable at 60% zoom
  - keep hands genuinely private, enforced by project(), never by CSS
  - make "show this card to Ana" and "show this card to everyone"
    first-class, obvious, and distinct from playing a card
  - give the facilitator macros for: set up, deal the starting hands,
    call time on trading, collect everything back, and reset
  - provide a personal ranking strip - a private zone where a participant
    orders their own cards - and record the order at the start and at the
    end, because the difference is what the debrief is built from
  - append a legible event for every trade, reveal, and reorder

If any of that cannot be expressed in the YAML plus the escape hatch, do
not special-case it in the web layer. Extend the definition format, and say
in your summary what you extended and why.

Write the deck as data files, add it to `validate-games`, and build a
readable /exercises/value-cards/deck page a facilitator can print. Commit.
```

**What `cards.csv` needs to cover:** every card's name, a one-sentence definition, a fuller gloss, and an example of it in tension with another value - one row each. **What your pasted rules need to cover:** how many cards exist and how many each person starts with; whether cards are duplicated across hands; what a legal trade is and whether anything is required alongside it; how a trade is agreed; whether there are rounds and what ends one; and what the facilitator decides versus what the table decides.

---

## 11. Democracy Simulation

**Status: Waiting on the author's rules.**

Same shape. Written second because it inherits everything the first one proved.

```text
Read CLAUDE.md, sandbox/games/, and the Value Cards definition for house
style. Build the Democracy Simulation as a game definition.

The roles live in content/exercises/democracy-simulation/roles.csv (one
row per role: name, description, starting_information, image - `image`
names a file in the sibling images/ folder and is blank for a generated
role card) - fill it in completely before running this prompt; read it
rather than asking for the roles to be pasted in. The rest of the rules are below. Implement exactly
these. If anything is ambiguous or contradictory, STOP and ask rather than
guessing.

<<<PASTE THE REST OF THE DEMOCRACY SIMULATION RULES HERE - HOW MANY
PARTICIPANTS, WHAT IS BEING DECIDED, HOW PROPOSALS ARE MADE AND AMENDED,
VOTING, AND WHAT ENDS A ROUND>>>

REGARDLESS OF THE RULES, this exercise must:
  - support roles or positions assigned to seats, with a fair deterministic
    shuffle the facilitator can re-roll before the session starts, and a
    role card each person can read privately
  - carry proposals as physical objects on the table - a note piece anyone
    can read, with an author and an amendment history reconstructible from
    the event log
  - implement voting as a component with more than one method available -
    simple majority, approval, and ranked choice at minimum - because which
    method is used is itself one of the things the exercise is about. Show
    the count's workings in the result, not just the winner. Ties are
    reported as ties.
  - record each seat's vote and, separately and privately, the position
    they held before the discussion. The gap between those two is the most
    valuable thing this exercise produces.
  - make a speaking queue available as a table object, so nobody has to
    interrupt to be heard on the call
  - never declare a side correct. The result reports what the table decided
    and by what method, and stops there.

Unit-test each voting method against known tallies including ties and
spoiled ballots. Commit.
```

**What `roles.csv` needs to cover:** every role's name, a description, and what information or perspective it starts with - one row each. **What your pasted rules need to cover:** how many participants there are; what is being decided; how proposals are made and amended; who may speak when; how voting works and who is eligible; what ends a round; and what the facilitator controls.

---

## 12. Facilitator controls and the shared view

**Status: Not started.**

Built after the games, because only now do you know what actually needs a control.

```text
Read CLAUDE.md. Build the facilitator console and the spectator view.

CONSOLE - a panel on the facilitator's own screen, collapsible
  Macro buttons for the current game, grouped, with destructive ones
  confirmed. The three they will actually use - set up, deal, reset -
  are large and always visible.
  Seats: assign, rename, swap, make observer, remove, resend link, and
  see who is connected.
  A pause control that freezes all input and shows a "we're talking" card
  on every screen, for when the conversation leaves the table. This will
  be used constantly. Make it one press.
  Facilitation prompts from the game definition, one press to push one to
  every screen.
  A timer that is advisory: it shows, it chimes, it never forces anything.
  Table controls: clear all ink, unlock everything, recall all cards,
  snapshot the table, restore a snapshot.

SPECTATOR VIEW at /t/{code}/view
  A read-only view of the public table for someone screen-sharing to a
  room, or joining late, or observing. Larger type, no controls, no hand
  tray. It must contain no private information: write a test that asserts
  the spectator projection contains no component_id for any piece in a
  private or hidden zone.

HANDOVER
  If the facilitator disconnects for 60 seconds, any participant may claim
  the role, and the claim is logged as an event and announced.

Commit.
```

---

## 13. Reflection, debrief and the playtest record

**Status: Not started.**

The civic payload, and the reason to keep an event log. Without this the site is a toy; with it, it is an instrument.

```text
Read CLAUDE.md. Build the reflection layer and the session record.

DURING PLAY
Short private prompts a facilitator can push, appearing as a card that can
be answered or dismissed and never blocking the table: "What are you
protecting right now?", "What would change your mind?" Answers are private
by default; a participant may mark one to share.

AFTER PLAY - /t/{code}/debrief, built from real events, not opinion
  1. What moved - each person's ranking or position at the start against
     the end, side by side, no score attached.
  2. Where the table disagreed - the widest spreads, offered as openers.
  3. The turns - moments the log shows a mind changed: a trade accepted
     after a refusal, a vote different from the pre-discussion position.
     Quote what the person wrote or showed at the time.
  4. Steelman - each person states in one sentence the strongest version
     of a position they argued against; shown beside what that person
     actually argued, once everyone has submitted.
  5. Open floor - shared reflections posted together, attributed, in the
     order written.
Charts are small, honest and unglamorous: one shared scale, direct labels,
theme tokens, no gradients. Never rank people.

THE RECORD
  Export a session as JSON (full event log, schema-versioned, with a data
  dictionary) and as CSV, from the facilitator console.
  An anonymised export replacing names with stable pseudonyms.
  Session replay: a /t/{code}/replay page that plays the event log back on
  a read-only table with a scrubber. This falls out almost free from the
  seeded RNG and the append-only log, and it is the single most useful
  thing you will have for improving the exercises.
  Timing derived from events: how long each part actually took, where
  people sat idle.

CONSENT
  A plain-language notice on joining: what is recorded, that this is a
  playtest, how it will be used, how to ask for deletion. A CONSENT.md in
  the repo. Do not skip this - you are recording people's arguments.

Commit.
```

---

## 14. Access, tablets and resilience

**Status: Not started.**

The pass that decides whether a real session survives contact with a real room. Do not defer it to "polish".

```text
Read CLAUDE.md. Harden the Ethics Sandbox. Behaviour changes only where
they are bugs.

ACCESSIBILITY
  Every table action reachable by keyboard: tab between pieces in a stable
  order, arrow keys to move, Enter to flip, a keyboard-openable context
  menu, and a keyboard route into and out of the hand tray.
  A live region announcing reveals, deals, macro results, and who joined
  or left. Not every piece movement - that would be unusable.
  Correct roles and labels on custom controls. AA contrast in both themes.
  Seat tints distinguishable under deuteranopia and protanopia, and never
  the only carrier of information - pair every tint with a name or shape.
  All motion behind prefers-reduced-motion, including piece interpolation.

DEVICES
  Laptop and tablet are the primary targets; make both genuinely good.
  Touch: drag, pinch zoom, two-finger pan, long-press menu, and a hand tray
  that works with a thumb. No hover-only affordances anywhere.
  Phone gets a reduced but honest view: your hand, the public table
  read-only, and the ability to show and play cards. Say plainly on the
  join screen that a larger screen is better.

RESILIENCE
  Locked phone or backgrounded tab resumes correctly.
  30 seconds of airplane mode recovers without a reload.
  Refresh mid-session restores exactly, including hand and zoom.
  Two people dragging the same piece resolves without either seeing a
  glitch.
  A dropped participant's held pieces release after 10 seconds.
  Error boundaries on every route with a message saying what happened and
  what to do next.

Commit.
```

---

## 15. Tests

**Status: Not started.**

```text
Read CLAUDE.md. Bring the test suite up to the standard the project needs.

  Model: full unit coverage of every operation and rejection, plus the
  Hypothesis properties from Prompt 4. This is the suite that matters.
  Games: every definition validates; every macro applies and is atomic;
  every escape-hatch function is unit-tested; a golden test that setup
  produces the expected table for each exercise.
  Realtime: ordering, reconnect with a gap, duplicate and out-of-order
  intents, backpressure, contested grabs.
  Security: a test that asserts no websocket message and no HTTP response
  contains a component_id the recipient is not entitled to, exercised
  against a recorded session of each exercise.
  End to end with Playwright: four browser contexts in one room playing
  each exercise through a full session, including a mid-session disconnect
  and rejoin, and a macro pressed while someone is mid-drag.
  A load check: 8 participants, 300 pieces, 10 minutes of continuous
  activity, memory flat and no message backlog.

Wire it all into CI. Commit.
```

---

## 16. Launch pass

**Status: Not started.**

```text
Read CLAUDE.md. Prepare the Ethics Sandbox for its first real session.

  Deploy to Fly.io or Render with staging and production. Websockets need
  a persistent process - document that constraint. Every environment
  variable in .env.example and the README.
  A seed command creating a demo table with fake participants, so an
  exercise can be shown without a group.
  OG images per exercise, favicon, correct titles.
  A FACILITATING.md: how to run each exercise, timings that actually work,
  what to do in the first two minutes while people find the link, the
  three failure modes to watch for, and what to do when the table goes
  quiet.
  A ROUGH-EDGES.md listing every known limitation and shortcut, honestly.
  Finally, walk the whole thing twice: once as a facilitator setting up a
  session five minutes before it starts, once as a participant on a tablet
  who has never seen it. Write up every friction point as a numbered list
  with a proposed fix, ordered by how likely it is to spoil a real
  session. Do not fix them in this pass - report them.
```

---

## How to run the series well

One prompt, one session, one commit. If an agent drifts into the next prompt's territory, stop it — the boundaries are what keep the codebase coherent.

Prompt 4 is the one to read carefully before accepting. Ask the agent to walk you through `project()` line by line and to show you the Hypothesis properties it wrote. Everything downstream — private hands, deliberate reveals, the spectator view, the exports — is that one function being correct.

Prompts 10 and 11 depend on your written rules and on the content/exercises/*/*.csv files being filled in first - the CSV carries the cards or roles themselves, the pasted rules carry everything about how they're used. Before sending either, read your rules as a stranger would and check they answer: how many people, what each person holds, what a legal move is, who may see what and when, how a round ends, and what the facilitator decides versus what the table decides. Anything they don't answer, the agent will answer for you.

After Prompt 9, ask what it would take to add a third exercise. If the answer involves writing Python outside `sandbox/games/`, the definition format isn't finished, and it is cheap to fix there and expensive to fix later.
