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

Prompts 1–9 are done. Prompt 10 (Value Cards Trading) is ready to run:
its rules and deck are now in this plan. Prompt 11 (Democracy Simulation)
is ready to run: its cards, sheets and invitations are in `content/`. Prompts 12–14 were rewritten on
2026-10-30 for the two exercises as they actually are. Prompt 12 now keeps
the facilitator's controls to what these two exercises need.

**The order from here is 17, then 10, then 12, then 11, then 13
and 14.** Prompt 17 (open rooms and activities) was added on 2026-10-31
and comes first: Prompts 10, 11 and 12 start activities inside the rooms it
builds. Prompt 10 has a paused draft, pull request #16; see its section. Prompt 14 does not depend on the games and can run alongside the
others.

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
| 9 | Game definitions and macro buttons | Done | | PR #9 |
| 10 | Value Cards Trading | Done | | PR #16 |
| 11 | Democracy Simulation | Done | | PR #19 |
| 12 | Running a session (rewritten, lean) | Done | | PR #20 |
| 13 | Reflection, debrief and the playtest record | Done | | PR #23 |
| 14 | Access, tablets and resilience | Done | | PR #24 |
| 15 | Tests | Not started | `claude/step-15-tests` | |
| 17 | Open rooms and activities | Done | | PR #18 |
| 16 | Launch pass | Not started; hosting is the Mac on the local network (below) | `claude/step-16-launch-pass` | |

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

- **Prompt 3.** The `/exercises` and `/about` routes do not
  exist; the site has `/` and `/exercises/{slug}` only. No page sets OG
  meta tags. The exercise page's "preview image" is an HTML mock-up built
  from `content/site/exercise_preview_*.csv`, not an image of a real table.
- **Prompt 5.** Closed by Prompt 13 (PR #23): rooms are dormant after 12
  idle hours and purged after 30 days, and the join notice and the
  facilitator's view say so.
- **Prompt 2.** `/styleguide` still describes the design as a "scholarly
  edition", which CLAUDE.md now rules out. Being removed in a separate PR.
- **CI.** `.github/workflows/ci.yml` runs Ruff (lint and format), mypy,
  pytest and the Playwright suite on every pull request. Prompt 15 still
  adds the load check and the recorded-session security test.

## Changes since the plan was written

Where these conflict with a prompt below, these win.

- **Two Doors, now Pairs.** Prompt 9's reference game was a test fixture,
  Two Doors, and on 2026-10-31 the author had it replaced by Pairs
  (`tests/games/pairs/`: deal three cards each, and whoever holds two of a
  rank has caught a pair). It is not part of the product, at the author's
  decision. Button wording is a per-game CSV, not YAML.
- **Voice.** Prompts 1 and 2 describe the look and voice as a "scholarly
  edition". CLAUDE.md now says to avoid that framing and keep the register
  plain and direct.
- **Editorial text lives in CSV.** All site copy, and each exercise's deck
  or roles, is in `content/` as CSV (see `content/README.md`). A prompt
  that says to write copy or decks in Python, templates or YAML should put
  the editable text in CSV instead.
- **Images as card faces.** A card or role may be an uploaded image, named
  in the `image` column of its CSV. Prompts 9–11 already say so.
- **Deployment.** Section 0 and Prompt 16 say Fly.io or Render. The
  author decided on 2026-10-30 to host from a MacBook on the local network
  for now, with `scripts/deploy.sh`. Prompt 16 deploys nowhere else, and
  Prompt 14 covers what serving from a Mac requires.
- **Exercise rules.** The rules for both exercises now come from the
  Center's own documents (linked under Prompts 10 and 11). They differ
  from what the first drafts of those prompts assumed. Value Cards is for
  exactly three people, with open hands. The Democracy Simulation is 9–20
  people per city, with a simple majority or a secret council vote. Where
  the site copy in `content/site/exercises.csv` says otherwise, Prompts 10
  and 11 correct it.
- **A room is an open sandbox; an activity is started inside it** (the
  author, 2026-10-31; superseding the 2026-10-30 note that a room is sized
  by its exercise). A room takes up to 30 people. An activity's seat range
  is how many people it takes: Value Cards Trading takes 3, and a Democracy
  city takes 9–20. A class larger than one activity runs several at once in
  one room, so Prompt 12 no longer needs several rooms. The facilitator is
  an optional admin seat that nobody holds by default. Prompt 17 builds
  this; CLAUDE.md's "Rooms and activities" is the rule.
- **Call.** Section 0 says Zoom; CLAUDE.md says a separate video or phone
  call. Nothing depends on which.
- **No principles of engagement.** The six principles that were on the
  landing page were drafted during the build, not taken from the Center,
  and the author removed them for good. Prompt 3 no longer asks for them;
  do not write new ones or add a `/principles` page.
- **Branches and pull requests.** CLAUDE.md now requires a descriptive
  branch name, a pull request for every pushed branch, and a "Questions for
  the author" section in every pull request description.

## Waiting on the author

- **Prompt 10:** nothing; its rules, deck, pictures and icons are all in
  the repo.
- **Prompt 11:** nothing; its text, role icons and city seals are all in
  the repo.

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
/about             What this is and who made it

LANDING
Open with the premise, not a slogan: one sentence on what the Ethics
Sandbox is, one on what a session is actually like - a group on a call
together, moving cards on a shared table, arguing - and two actions,
"Start a table" and "See the exercises". Then a short section on the shape
of every exercise here: play, then argue, then look at what you did. Then
the two exercise cards. No hero image, no viewport-height opener, no
testimonials.

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

**Status: Done (PR #9).**

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

**Status: Done (PR #16).** Built: the swap and owner-moves-only model, Value
Cards Trading as an activity (3 players, started from an open room),
`record_hands`, the debrief prompts, the catalog row, the card faces (group
frame, Schwartz icon, picture), the table client's offer controls and pair
checklist, and the printable deck page. Not built: a snapshot of each hand
as dealt (the deal is in the log and replays to it). The rules and the
deck below were copied on
2026-10-30 from the Center's Civil Discourse Wiki on Notion. The pages
render only with JavaScript: a plain fetch returns an empty page, so open
them in a browser (or headless Chromium) to check them.

- Rules: "Core Value Cards Activity: Trading & Sorting",
  <https://harvard-ethics.notion.site/Core-Value-Cards-Activity-Trading-Sorting-3b9fa270aa9380a0a889f27be7fdae5d>
- Deck: the printed cards (the author's decision, 2026-10-30). They are
  printed with nanDECK from the "deck" sheet of the author's Google Sheet
  "values cards - the spreadsheet"
  (<https://docs.google.com/spreadsheets/d/1bsJuX048BY9O0T0C2chUs7qZin4K5ibCWq4ek1lDvT4/edit>).
  The print script, `valuecards.txt` in the Drive folder "Value Cards",
  prints the rows marked Deck (18) and Sidebar (18) and leaves out
  Archive. The resulting file is `valuescards.pdf` in the same folder.
  The 36 cards are now in `content/decks/value-cards/cards.csv`. They live
  outside any one exercise because later exercises will use the same
  deck. The Kit page on Notion
  (<https://harvard-ethics.notion.site/Value-Cards-Kit-372fa270aa9380e184d2fbe263ce96d2>)
  lists the same 36. Its "+ 1" marks are a Notion link to a second Schwartz
  category, not something printed on the card, and the deck does not
  carry them.
- The Kit also links a digital version on Screentop
  (<https://screentop.gg/@tperry/value-cards/play/skwb>). It is useful for
  comparing layouts. Do not copy it.

### The rules, as the activity page gives them

- **Group:** exactly three players. A class runs as many trios as it
  needs, side by side.
- **Time:** about 30 minutes, followed by a debrief.
- **Deal:** the deck is split equally among the three players, so 12 cards
  each.
- **Hands are open.** Players keep their cards face up "so that all
  players can see each other's cards throughout the game".
- **Goal:** build the hand that best reflects the values you care about
  most, by trading.
- **A trade** is an exchange of the same number of cards in each direction.
  There are no one-sided gifts. Players may trade as often as they like,
  but each player must trade at least once with each of the other two
  before the exercise ends.
- **Sorting:** once trading has finished, each player picks the top three
  values in their final hand.
- **Sharing:** players may share their decisions and their final values
  with the trio, or with people outside it, if they choose. Doing so is
  optional.
- **Sensitivity** (the activity page's own rating): "Low to Moderate —
  trading and final hands are visible within the trio throughout, and
  sharing beyond the group at the end is optional".

The debrief questions on the activity page:

1. How strongly do you feel about the values you prioritized?
2. What experiences or influences have shaped the values you hold most
   strongly?
3. Did this reflection reinforce or challenge any of your existing beliefs?
4. Were there moments when you second-guessed your decisions? Why?
5. How did the group dynamics influence which values were chosen? How
   might the result have been different if there were different members?
   What was your role in this group dynamic?

Additional questions:

6. Do you think your values would change if you did this activity in a
   different phase of your life?
7. Are there areas in your life where your actions don't fully align with
   your values? How might you bridge that gap?
8. In what ways do your values guide your relationships, career choices,
   or goals?
9. How might this reflection shape the way you navigate ethical dilemmas
   in the future?
10. If someone were to observe your actions, what values do you think they
    would say you prioritize?
11. What is one value you want to be more intentional about upholding?
12. Did the group make any decisions that reflected shared values?

### The deck as printed

`content/decks/value-cards/cards.csv` has one row per printed card: key,
name, definition, group (Deck or Sidebar), number (the number printed in
the card's corner), schwartz (the Schwartz category whose icon is printed
beside the number), art and image.

The printed face, from the print script, is: the name in title case
("Community"), the definition beneath it, and the card's picture in the
lower half (`<Name>.png`, from the Drive folder "Value Cards/images 2.1").
The number and the Schwartz icon sit in the bottom corner. A crimson frame
(`#A41034`) marks a Deck card and a navy one (`#172D4A`) a Sidebar card.
The back is the Center's seal, which is already the platform's card back.

`art` names the picture file. `image` stays blank, so the face is
generated from text plus the picture and the text stays real text at any
zoom. The pictures are in `content/decks/value-cards/images/` and the
Schwartz icons in its `icons/` folder, all exported from Drive and checked
against Drive's file sizes. Most pictures are 2000x2000. Two are not:
Leadership is 1999x1545 and Dignity is 1470x1470. Fit each picture inside
its box without cropping or stretching. The same goes for the Democracy
Simulation's river-resident icon, which is 2172x724.

The definitions are copied from the sheet as they stand. Two differ from
the Notion page by a serial comma ("connection, and care";
"opportunities, and respect"), and they match the printed PDF.

### What changed from the prompt as first written

The first version of this prompt was written before the rules existed, and
four of its requirements contradict them. Each is replaced below:

- **Hands.** The first version said hands were private. In the activity
  they are open within the trio.
- **Card fields.** It asked for a fuller gloss and a tension example on
  every card. The printed cards carry a name, a definition, a picture, a
  number and a Schwartz icon.
- **Ranking.** It asked for a ranking strip with the order recorded at the
  start and the end. The activity's sorting step is choosing a top three
  at the end.
- **Group size.** It assumed 4–12 people. The activity is for three.

```text
Read CLAUDE.md, sandbox/games/, and the Pairs fixture
(tests/games/pairs/ with its CSVs). Then build the Value Cards Trading
exercise as a game definition. The rules, the deck and the debrief
questions are in docs/BUILD-PLAN.md under Prompt 10. Implement exactly
those rules. If anything there is ambiguous, contradictory or incomplete,
STOP and list the questions rather than guessing. Mark anything you have
to invent with a TODO comment.

CONTENT
  The deck is content/decks/value-cards/cards.csv, already filled in
  from the printed cards (see "The deck as printed" in the plan). Name it
  from the game's components; do not copy it into the exercise's folder.
  Draw each face as printed: name, definition, the picture named in
  `art`, the number with its Schwartz icon, and a frame coloured by
  `group`, using colours from tokens.css and adding tokens if needed. If
  the definition format cannot name a picture column alongside text, add
  that in generic terms. The debrief questions go in the game's prompts
  CSV. Update the exercise's
  row in content/site/exercises.csv to match the activity: three people
  per table, any number of tables, about 30 minutes plus a debrief.

THE TABLE
  meta.players is min 3, max 3. The facilitator is optional: a trio can
  run it alone, and the teacher looking after several trios is Prompt
  12's business.
  Each seat has a hand. The hand is visible to everyone at the table, but
  only its owner may move cards within it or out of it. If the model has
  no way to say "public, but only the owner moves it", add one, in
  generic terms, to sandbox/model/. A rule like that is not specific to
  this exercise.
  Each seat also has a top-three zone with capacity 3, private to its
  owner. Sharing it is the owner's choice, made with the existing reveal
  ("show to the table"). Nothing ever reveals it automatically.
  Card faces must be readable at 60% zoom with 12 cards in a hand.

TRADING
  A trade is an offer: one player picks N of their own cards and N of
  another player's, with N at least 1, and the other player accepts or
  declines. The offerer may withdraw it until it is answered. Acceptance
  swaps the cards as one transaction. Unequal counts, gifts (N for 0) and
  taking a card out of someone else's hand are all refused by Python, each
  with a plain sentence. While an offer is open, everyone at the table
  can see it.
  The exchange is a generic model operation: an atomic swap between two
  owners' zones, agreed to by both. It must not be written as anything
  specific to value cards.
  The table shows, for each pair, whether that pair has traded yet. It is
  a checklist, not a score.

MACROS (every game also has setup, deal, reset, shuffle, collect and
clear_ink)
  deal: 12 cards to each seat, face up.
  record_hands (the author, 2026-10-31: trading has no time limit, so this
  replaces call_time and ends nothing): keeps a record of every hand and of
  the pairs that have not traded, named in the record. It never blocks.

EVENTS
  Log every offer, acceptance, refusal and withdrawal, and every move into
  or out of a top-three zone. Record each seat's hand as dealt and as it
  stands when record_hands is pressed. Prompt 13's debrief is built from these.

Tests: equal-count enforcement, the refusal of gifts and taking, the
atomic swap, the pair checklist, and dealing 12 each. validate-games must
pass. Build a printable deck page at /exercises/value-cards-trading/deck.
Update this plan's status table. Commit.
```

---

## 11. Democracy Simulation

**Status: Done (PR #19).** Built: options (city and
phase), the cards, the deal, the co-Chairs, written proposals, the speaking
queue, and the count in both cities, with tests. The author decided on
2026-10-31: text can be written on a note (a generic `SetText`, by
double-click); a co-Chair or king calls a vote on one written proposal moved
onto the floor; a vote is a show of hands, so a proposal passes when more than
half of those present are for it and anyone without a hand up is against;
the council is the kings, merchants and nobles. All of the material is in the author's Drive
folder,
<https://drive.google.com/drive/folders/1zRzxok62G8tFtLYkgUMj_4d0JtB6nqOa>,
read on 2026-10-30:

- **"Leadership and knowledge in democracies and oligarchies"** (Tomer J.
  Perry): the rules, read in full (both tabs). Its "Running the exercise
  remotely" and "Observation Sheet" headings are empty so far.
- **"role cards"** (a Google Sheet): all 80 cards, 20 per city per scenario,
  plus the job, feature and moderator text. These are now exported to
  `content/exercises/democracy-simulation/` as `roles.csv`, `jobs.csv` and
  `features.csv`. The values are unchanged; only the whitespace was tidied.
- **The four "Printouts" Google Docs,** one per city per scenario: each
  city's invitation and its five elite information sheets. Scenario 2
  Potamosia is the clean copy the author made on 2026-10-30
  (<https://docs.google.com/document/d/1nNzufIhuVVw9oXG1NVnZRjUwBYiYLFYA-JroTQII5jo/edit>),
  not the older doc with suggested edits. All four are exported to
  `invitations.csv` and `elite_sheets.csv`, with the typos listed below
  corrected at the author's request.
- **"Democracy Simulation: Slides",** the introduction deck.
- **The `role-icons` folder** (an icon per job, plus moderator and river
  resident) and the two city seals, for card faces.

### The rules, as the document gives them

- **Groups:** each city is 9–20 participants, and a class runs several
  cities at once. One room is one city.
- **Two cities, two variants.** Potamosia is a democracy. Hudrosia is an
  oligarchy. Their citizens are identical: the same roles, interests and
  knowledge. The one difference in the cards is that Potamosia's two
  mayors are Hudrosia's two kings. A class runs either democracy-only
  cities or half and half.
- **Two scenarios.** Each is a separate session, and either can be run
  alone. Scenario 1, "Construction Project": the city has 30 gold, enough
  for one of three projects (the dam, real cost 18; the bridge, 20; the
  walls, 21). The richer citizens' private wealth could pay for all
  three, but that is not public. Scenario 2, "Going to war?": the choice is
  attack, defences or diplomacy. The outcome depends on what the other
  city chooses, through a three-by-three outcomes table that forms a
  cycle like rock-paper-scissors.
- **Role cards.** Every card is numbered 1–20. A city of N people uses
  cards 1 to N, which keeps support for each option balanced at every
  size. Each card has a job (Mayor/King, Merchant, Noble, Mason, Farmer,
  Shepherd, Thespian or Fisher), an interest and some knowledge. Some
  cards also mark the holder as a river dweller, and some carry a rumour.
  A card's secret side is never shown to anyone: holders may tell others
  what it says, or not tell them. Its public side carries a character
  name, which the player chooses and introduces in character ("I am
  Felix, the Farmer").
- **Elites.** The Mayors/Kings, Merchants and Noble are 25–40% of the city.
  They also receive an information sheet. The sheets are largely
  accurate, but they disagree with each other on estimates.
- **Potamosia (democracy):** decisions are by simple majority of all
  present citizens. By custom the mayors speak first. They are elected
  yearly and can be deposed by majority vote. Two citizens are picked at
  random as co-Chairs (moderators). The co-Chairs grant and revoke the
  right to speak, draft resolutions and call votes. They must see at
  least one proposal affirmed, or be exiled.
- **Hudrosia (oligarchy):** a council of the elite decides, run by the
  two hereditary kings, in a fishbowl with the rest of the city looking
  on. In principle it decides by consensus; in practice by a majority in
  a secret council vote. At least one proposal must pass in the first 20
  minutes. In the last 10 minutes the kings hold a public assembly where
  townspeople can question and heckle.
- **Timing:** an introduction of 5–10 minutes, then 30 minutes of meeting
  with a visible timer, then the debrief.
- **Debrief:** questions grouped under three learning outcomes. The
  document suggests the instructor observes during play and debriefs from
  those observations.

### Decided by the author on 2026-10-30

- **Jobs are public.** Everyone can see who is a farmer and who is a
  shepherd. Everything on the back of a card, and the elite sheets, is
  private, and stays private at the debrief too.
- **Potamosia votes by a show of hands,** so each person's vote is public.

### Checked against the document

- The card order in `roles.csv` matches the document's role mix at every
  size from 9 to 20, in both scenarios.
- The river and rumour counts match the document's shares: in Scenario 1, 7
  river dwellers and 5 rumours at 20; in Scenario 2, 8 river dwellers (40%)
  and 6 rumours (30%) at 20.
- Elite sheets exist for exactly the elite card numbers: Scenario 1 cards
  1, 10 (Mayor/King), 2, 4 (Merchant) and 14 (Noble); Scenario 2 cards 1, 10,
  4, 13 (Merchant) and 7 (Noble).

### Resolved by the author on 2026-10-30

- The Scenario 2 Hudrosia council flags are corrected in the sheet: card 13
  (a Merchant) is on the council and card 2 (a Shepherd) is not.
  `roles.csv` was re-exported to match.
- A card that is both a council member and a river dweller shows both
  lines. The sheet now gives Scenario 2 Hudrosia cards 1 and 4 both.
- The repeated title line on the Scenario 1 Hudrosia King card 1 sheet is
  gone.
- Where the slide deck and the printouts differ, the printouts are
  current.

### Typos corrected in the copy (the author's decision, 2026-10-30)

The Drive docs are unchanged. `invitations.csv` and `elite_sheets.csv`
correct these, the count being how many times each was found:

- "Hedrosia" to "Hudrosia" (5);
- "Potamsians" to "Potamosians" (10);
- "Potamsia's" to "Potamosia's" (1);
- "Potomosian" to "Potamosian" (2);
- "scuffles but i shepherds" to "scuffles but shepherds" (5);
- "the informed masses" to "the uninformed masses" (5);
- "increasingly outrageous and plans" to "increasingly outrageous plans"
  (5);
- "manner of Potamosians Demokrats" to "manner of Potamosian Demokrats"
  (2);
- "provoking shuffles" to "provoking scuffles" (1);
- "and if respond in kind" to "and if they respond in kind" (10);
- "Against the background" to "Against this background" (4);
- "but this it will guarantee" to "but this will guarantee" (1);
- "troubling.The" to "troubling. The" (1);
- "answer what questions from the people raise" to "answer what
  questions the people raise" (1);
- "river,close" to "river, close" (1);
- "about half the city. would" to "about half the city, would" (1);
- "a half an hour Sand Timer" to "a half-hour Sand Timer" (1);
- doubled spaces, wherever they appeared.

The text keeps the printouts' emphasis (the author's decision,
2026-10-30). It is written in a small subset of Markdown:
- `**bold**` and `*italic*`;
- `# ` for a heading line;
- a blank line between paragraphs;
- list items starting with "- " (or "1. " in an invitation);
- `\*` for a literal asterisk.

Prompt 11 renders that subset on the card and sheet faces, as real text,
and nothing more.

### What changed from the prompt as first written

The first version asked for approval and ranked-choice voting, and for a
private pre-discussion poll. The document has neither. It uses a simple
majority in Potamosia and a secret council majority in Hudrosia. The
"position before discussion" already exists: it is the interest printed on
each person's role card.

```text
Read CLAUDE.md, sandbox/games/, and the Value Cards Trading definition for
house style. Then build the Democracy Simulation as a game definition. The
rules are in docs/BUILD-PLAN.md under Prompt 11, and the full source is
the author's document linked there. Implement exactly those rules. If
anything there is ambiguous or contradictory, STOP and ask rather than
guessing.

CONTENT, in content/exercises/democracy-simulation/
  Already there, exported from the author's "role cards" sheet:
    roles.csv: key, phase, city, card_number, job, river, rumour, council,
    image. 80 rows, one card each.
    jobs.csv: key, phase, job, elite, knowledge, interest, image. This
    includes the Moderator card's text.
    features.csv: key, phase, feature (River, Rumors, Council), knowledge,
    interest.
  A card's back is its job's knowledge and interest, plus the line from
  each feature it has.
    elite_sheets.csv: key, phase, city, card_number, job, text. One row per
    elite card (20). Text in both files uses the small Markdown subset
    described under "Typos corrected in the copy".
    invitations.csv: key, phase, city, text. One row per city per scenario
    (4).
  To add, from the rules document:
    outcomes.csv: our_choice, their_choice, text (Scenario 2).
  images/ holds the job, moderator and river-resident icons and the two
  city seals (potamosia-seal.png, hudrosia-seal.png), exported from the
  author's Drive.
  The debrief questions go in the game's prompts CSV, each with the
  learning outcome it belongs to.
  Update the exercise's row in content/site/exercises.csv: 9–20 people per
  city, several cities at once, and the real running time.

OPTIONS
  The room is created with two choices: city (Potamosia or Hudrosia) and
  scenario (1 or 2; the column and option id stay `phase`). Add `options` to the definition format in generic
  terms: named choices offered on /start, and readable by steps and by
  rules.py through GameContext. Mayor/King is a label that depends on the
  city. Nothing in sandbox/web/ may know about either city.

SEATS AND CARDS
  meta.players is min 9, max 20.
  deal (rules.py): with N seats taken, shuffle cards 1..N and deal one to
  each seat, private to its owner. Elite cards also deal their sheet,
  also private. Re-dealing is allowed until the meeting starts.
  The role cards and sheets cannot be shown to anyone. Add a generic deck
  flag (`revealable: false`) that removes the reveal from the menu and
  that the model refuses.
  Each seat has a public name tent showing the job and a character name
  the player types. Jobs are public; the back of every card and every
  elite sheet is private, for the whole session and at the debrief.

POTAMOSIA
  choose_moderators: picks two seats at random (as a logged Shuffle, not
  global randomness) and gives each a public Moderator token and the
  moderator card. A speaking queue sits on the table: anyone can join it;
  the moderators and the facilitator can call the next speaker or clear
  it.
  A vote is called by a moderator or the facilitator (rules.py checks who
  holds the token). Every present seat votes once on the options, and
  votes are shown together when the count closes. Votes are public, like
  a show of hands. An option passes with
  more than half the votes cast. A tie is reported as a tie and nothing
  passes.

HUDROSIA
  At setup the elite seats' name tents sit in a council zone in the
  middle of the table. Votes are called by a king or the facilitator.
  Only council members vote, and the vote is secret: the table sees the
  tally; who voted for what is recorded but shown only to the facilitator.
  The meeting is in two parts: council (20 minutes), then public assembly
  (10 minutes). Both are advisory labels on the timer, not locks.

PROPOSALS
  A proposal is a note piece in a Proposals zone. Anyone may write one,
  and its author and edit history come from the event log. Putting a
  proposal to the vote moves it to "On the floor"; the result moves it to
  "Passed" or "Not passed".

SCENARIO 2
  Record the decision each city passes. Pairing two rooms and showing the
  outcome from outcomes.csv belongs to Prompt 12's class panel, not to
  this prompt.

EVENTS
  Record, for each seat: card number, job, the interest on its card, and
  each vote it cast. Prompt 13 compares interest with vote.

Unit-test the count: majority, a tie, nobody voting, and a secret council
vote that must not leak to the table's projection. validate-games plays
both cities and both scenarios at 9 and at 20 seats. Update this plan's
status table. Commit.
```

---

## 12. Running a session

**Status: Done (PR #20); what was left out is listed under "Deferred" below.** Restated on 2026-10-31 after the author's answers on
the pull request, to fit "A room is an open sandbox" (Prompt 17). The
2026-10-30 version, a class that owned several rooms with its own page at
`/c/{code}`, is withdrawn. The longer list from the first version is kept
under "Deferred" below.

Decisions (the author, 2026-10-31):

- **A class is a kind of activity with several tables.** In a sandbox room
  someone may start an activity, or start a class. A class starts one
  activity as several tables at once, each running it, all in the same
  room. The person who starts it becomes the facilitator of every table,
  as a non-playing admin: they are not seated at any table.
- **The room cap is 30** (was 20), so a class of 24 (eight trios) fits.
- **Sort at random: yes.**
- **The timer and pushed prompts go to every table at once.**
- **Pairing exists for Scenario 2 of the Democracy Simulation only.**
  Scenarios 1 and 2 are independent: a class may run either without the
  other. Value Cards Trading has no scenarios and no pairing.

```text
Read CLAUDE.md. Build what a facilitator needs to run a class through the
Ethics Sandbox, and no more.

A CLASS
  Beside "Start the <activity>", a room offers "Start a class": choose the
  activity, its options, and a number of tables. The tables are created in
  one transaction, whole or not at all, in the same room. The starter
  takes the facilitator seat (if another person holds it, the starter
  must be that person) and is not seated at any table.
  The class panel, seen by the facilitator: one row per table, showing who
  is seated, who is connected, and whether its macros have run (set up,
  dealt, time called), and a button to go to that table's zones.
  The class panel, seen by a participant: the tables with open seats. They
  choose one. The facilitator can also move a participant between tables.
  Sort at random: one press deals everyone in the room who is not seated
  into the class's tables at random, as evenly as each table's player
  range allows. It is a logged shuffle, not global randomness. It is shown
  before it is applied, and the facilitator can sort again or adjust by
  hand before confirming. People who arrive later are placed in the table
  with the most room.
  The panel never shows a card face or a token value. Test that.
  The facilitator is recognised by the existing identity cookie.

IN EACH TABLE
  The macro toolbar already exists. Add a roster showing who is connected
  and who is away. The facilitator gets "make observer" and "remove",
  using the existing room services.
  A timer: the facilitator starts it for every table of the class at once.
  Every screen shows the time remaining. It chimes once when it runs out.
  It is advisory and never refuses anything.
  Push a prompt: the facilitator picks one of the game's prompts and shows
  it as a dismissable card on every screen of every table.

PAIRED TABLES (Democracy Simulation, Scenario 2 only)
  The facilitator pairs two tables of a class. Once both have passed a
  decision, the panel shows the facilitator the matching row of
  outcomes.csv. The facilitator decides when to announce it. This is game
  data read through the definition; the web layer only knows that a game
  may declare pairing.

Tests: a class of N tables is created whole or not at all; the panel leaks
nothing; a participant cannot act as facilitator on it; the timer running
out changes nothing on the table; a room accepts 30 people and refuses
the 31st. Update this plan's status table. Commit.
```

Settled on the pull request (2026-10-31): the facilitator may move anyone
between tables at any time, and a latecomer takes the roomiest table, begun or
not; a person moved off a begun table puts their cards back in their decks,
which are shuffled; the people at a paired table propose its choice and the
facilitator confirms it; the class has one timer; and the per-part meeting
label is dropped.

**Deferred** from the first version, to be added when a session shows
they are needed:

- the pause control that freezes the table;
- snapshots and restore;
- "unlock everything" and "recall all cards" as separate controls (the
  game's collect and reset macros cover most of this);
- swapping and renaming seats;
- the spectator view at `/t/{code}/view`, with its privacy test;
- facilitator handover after 60 seconds away.

---

## 13. Reflection, debrief and the playtest record

**Status: Done (PR #23).** Rewritten on 2026-10-30 for the two
exercises as they actually are.

Decided by the author on 2026-11-01 (these replace the prompt text below
where they differ):

- A debrief is an **activity**, like Value Cards Trading: it is started from
  the sandbox by someone who becomes its facilitator, not a page. There is
  one for each exercise (`value-cards-debrief`, `democracy-debrief`).
- There is **no consent statement** and no `CONSENT.md`; the join screen is
  unchanged.
- The facilitator exports some of the session's notes and text with
  **checkboxes**, not links.
- The debrief activity **draws on what was logged** at the exercise it
  follows; the facilitator picks which table's or class's record to open
  it with. Rooms still go dormant after 12 idle hours and are purged after
  30 days, and the facilitator can still delete a room's record.
- Each exercise's **learning outcomes** are shown on its page and are the
  cards on its debrief table (`content/site/exercise_learning_outcomes.csv`).

Built (PR #23):

- The two debrief **activities**, and each exercise's learning outcomes on
  its page.
- **Debrief pages**, keyed by activity or class (a room holds many):
  `/t/{code}/debrief`, `/t/{code}/debrief/{activity_id}` and
  `/t/{code}/class/{class_id}/debrief`. Each exercise's reading of the log is
  in its game package (`debrief.py`) and registers in
  `sandbox/games/debrief.py`; `sandbox/web/debrief.py` only draws it. The
  facilitator sees a page at any time and opens it to the room with one
  button; an ended activity or class can still be read, from the table as it
  stood. Charts are plain bars on one scale, tokens only; people are never
  ranked.
- **Observation notes** (facilitator only, tagged with an outcome, kept in
  the log as a `Record` named `observation`) and **reflections** at
  `/t/{code}/reflect` (private unless shared; shared ones show on the debrief
  without names).
- **Replay** at `/t/{code}/replay`: the table rebuilt from the log
  (`sandbox/web/replay.py`), read-only, with a slider; public view by
  default, every face for the facilitator on request. A test checks the
  rebuilt table equals the live one.
- **Timing** from event times on each debrief: the parts of the exercise and
  stretches with nothing logged.
- The export, retention, the facilitator's delete, and the Help page.

Added on the author's answers: an "Open the public assembly" button for
Hudrosia (a king or the facilitator; logged, shown in the timeline), and
shared reflections show their writer's name. The plan's `/t/{code}/debrief`
and `/c/{code}/debrief` became the activity and class routes above.

The point of this step is to give the debrief, which both source documents
say is where the learning happens, something accurate to work from. The
facilitator should be able to say "you gave away *justice* in your second
trade" or "the council voted three to two for the walls", not rely on
memory. The step has four parts:

1. Notes and reflections during play.
2. A debrief page for each table, and one for the class.
3. The record: exports and replay.
4. Consent, and what happens to the data.

**What the step can count on.** It is built only from events that Prompts
10–12 already log. It adds no new tracking of what people do at the
table.

**Where the debrief stops.** It never ranks or scores people, and it never
says which choice was right. Speech is not recorded. The platform cannot
know what was said on the call, so anything about the conversation comes
from the facilitator's notes, not from the software.

```text
Read CLAUDE.md, the two exercise definitions, and docs/BUILD-PLAN.md
under Prompts 10-13. Build the reflection layer and the session record.

DURING PLAY
  Observation notes (facilitator only): a notes box on the class page and
  on each table. Each note is timestamped, attached to that table's event
  log, and may be tagged with one of the game's learning outcomes (listed
  in the game's content). The Democracy Simulation document recommends
  exactly this: observe, note behaviour, then debrief from the notes.
  Reflection prompts: when the facilitator pushes a prompt (Prompt 12), a
  participant may answer it in a private text box. Answers are private by
  default. The participant may mark an answer "share with the table". The
  box never blocks the table and can be dismissed.

THE DEBRIEF PAGE: /t/{code}/debrief
  The facilitator sees it at any time. Participants see it once the
  facilitator opens it, with one button. Everything on it comes from the
  event log.

  Value Cards Trading
    Each person, side by side: the hand they were dealt, the hand they
    ended with (kept, given, received), and their top three if they
    chose to show it. A top three that was not shown is visible only to
    its owner, on their own debrief.
    The trades in order: who gave what for what, and when. Also the
    offers that were declined and the cards they asked for.
    Across the trio: cards that changed hands most, cards that never
    moved, and cards nobody put in a top three.
    The activity's debrief questions, listed for discussion.

  Democracy Simulation
    A timeline: when the moderators were chosen; each proposal as
    written, who wrote it, its edits, when it was put to the vote, and
    the result; and, in Hudrosia, the change from council to assembly.
    Each vote: the tally per option. In Potamosia, how each person voted.
    In Hudrosia's council, the tally only, unless the facilitator
    chooses to show more.
    Interest against vote: for each person, the option their card
    favoured and the way they voted. The facilitator sees all of it;
    each participant sees only their own. Jobs are public throughout,
    but the back of a card is never shown to anyone else.
    Information that existed in the room: every knowledge item and
    rumour on the cards dealt. The facilitator ticks the ones that
    surfaced (the software cannot hear the call), or picks them from
    their notes.
    Scenario 2: the decisions of the two paired cities and the outcome.
    The document's debrief questions, grouped by learning outcome.

THE CLASS DEBRIEF: /c/{code}/debrief
  Value Cards: which values were kept and which were given away most
  often, across all trios. No trio is compared with another.
  Democracy Simulation: each city's decision side by side, with the
  democracies and the oligarchies in separate columns. The document
  calls this a controlled experiment, so put the comparison first.

CHARTS
  Small and plain: one shared scale, direct labels, colours from the
  design tokens only, no gradients. Never rank people.

THE RECORD (facilitator only)
  Export a table or a whole class as JSON: the full event log,
  schema-versioned, with a data dictionary (docs/DATA-DICTIONARY.md)
  explaining every event type and field. Also as CSV, one file per event
  type.
  An anonymised export: names replaced with stable pseudonyms
  (Participant A, B and so on, stable within one export), and free text
  (notes, proposals, reflections) left out unless the facilitator ticks
  "include written text".
  Replay at /t/{code}/replay: the table rebuilt from the event log, with
  a scrubber, read-only. By default it shows the public view; the
  facilitator may replay showing every face.
  Timing from events: how long each part took (dealing to calling time,
  each vote), and stretches where a table was idle.

CONSENT AND RETENTION
  The join screen carries a short, plain notice: what is recorded (moves,
  votes, written text, display names, never audio or video), that this is
  a playtest, how the record is used, and how to ask for it to be
  deleted. Add CONSENT.md, written in the same words.
  The facilitator can delete a table's or a class's record outright.
  This also closes the Prompt 5 gap: rooms go dormant after 12 idle
  hours and are deleted after 30 days. Say so in the notice, and in the
  facilitator's view of the room.

Tests: each debrief section against a recorded session of each exercise;
the anonymised export contains no display name; an unshown top three and
the Hudrosia council's individual votes never reach a participant's
debrief before they should. Update this plan's status table. Commit.
```

---

## 14. Access, tablets and resilience

**Status: Done (PR #24).** Rewritten on 2026-10-30 to account for what
Prompt 8 already did and for hosting from a Mac on the local network.

**Already in place, so this step checks it rather than builds it.**

- **Keyboard (Prompt 8):** Tab to every piece, arrow keys to move, Enter
  to flip, R to rotate, M or Shift-F10 for the menu, P to point, Escape
  to clear.
- **Announcements:** a live region (`client/src/announcer.ts`).
- **Touch:** a 500 ms long press opens the menu (`client/src/interaction.ts`),
  and pinch zoom works (`client/src/viewport-input.ts`).
- **Reduced motion:** `prefers-reduced-motion` is checked in
  `client/src/table.ts` and the stylesheets.

**Found while revising this plan:**

- **Holds.** When a participant's socket closes, their held pieces are
  released at once (`sandbox/web/live.py`, `_on_leave`). The plan asked
  for a 10-second grace period.
- **Copying the room link.** The "copy room link" button builds the link
  from the address in the browser's own bar
  (`sandbox/web/templates/table.html`).
  - On the Mac running the server, that address is `localhost`, so the
    link it copies is useless to anyone else.
  - On another device the address is `http://<LAN IP>`, which is not a
    secure context. There `navigator.clipboard` does not exist, the call
    throws, and the button silently does nothing.

```text
Read CLAUDE.md. Harden the Ethics Sandbox for a real session: laptops and
tablets in a classroom, served from a Mac on the local network. Change
behaviour only where it is a bug or this prompt says so. For every item,
write a test (Playwright where it involves a browser) or, where it
cannot be automated, a line in docs/MANUAL-CHECKS.md saying how to check
it by hand.

ACCESSIBILITY
  Check the keyboard model from Prompt 8 end to end, in both exercises:
  the trade offer, the vote, the speaking queue, and getting into and out
  of the hand tray and the top-three zone. Fix any gaps.
  Every custom control has a correct role and label. Check this with
  axe-core run from Playwright (@axe-core/playwright, approved by the
  author on 2026-10-30), and add its one-line justification to CLAUDE.md.
  Measure AA contrast for every text-on-surface pair in tokens.css, in
  both themes. List any failures and fix them in tokens.css only.
  Seat tints must be distinguishable under deuteranopia and protanopia,
  and must never carry information alone: a name or a shape always goes
  with them.
  prefers-reduced-motion must cover piece interpolation, the rollback
  glide, toasts and the timer.
  The announcer says: deals, trades accepted, votes opened and closed,
  reveals, macros, joins and leaves. It does not announce ordinary moves.
  The page works with text zoomed to 200%.

TABLETS AND PHONES
  Targets: iPad in Safari (portrait and landscape) and a laptop at
  1280x800. Run the Playwright suite in WebKit as well as Chromium, in CI
  (approved by the author on 2026-10-30).
  Touch: one-finger drag, pinch zoom, two-finger pan, long-press menu,
  tap to select. Make the trade offer and the vote work by touch alone.
  Touch targets are at least 44 px. Nothing works only on hover.
  The hand tray and its 12 cards fit within thumb reach in both
  orientations. Rotating the iPad keeps your place on the table.
  The on-screen keyboard does not cover the note or name being typed.
  Phones (narrower than 600 px): your hand and private cards, the public
  table read-only, and the actions to show or play a card, offer or
  answer a trade, and vote. The join screen says plainly that a tablet
  or laptop is better.

SERVING FROM A MAC ON THE LOCAL NETWORK
  Links shared from the Mac must use its network address. scripts/deploy.sh
  sets SANDBOX_PUBLIC_URL from the LAN IP. The app builds every shareable
  link from that setting, and shows the link as text that can be selected
  and copied by hand.
  Copying must work without a secure context. Where navigator.clipboard
  is missing, select the link text and say "Press Ctrl-C or Cmd-C".
  Audit the client for any other API that needs a secure context.
  Add a /health page a participant can open to check they can reach the
  Mac at all.
  A server restart mid-session (Ctrl-C, then deploy.sh again) restores
  every table from its snapshot, and the clients reconnect on their own.
  docs/FACILITATING-ON-A-MAC.md:
    - keep the lid open and the charger in (caffeinate -i stops idle
      sleep, not sleep when the lid is closed);
    - campus and guest Wi-Fi often stop devices from reaching one
      another, so test the network beforehand, or use a hotspot or a
      router of your own;
    - what to do if the Mac's address changes;
    - check /health from one tablet before the class arrives.

RESILIENCE
  Each of these is a Playwright test:
  - A tab that was backgrounded, or an iPad that was locked, picks up
    again on its own, replaying from the last seq it saw.
  - 30 seconds offline recovers without a reload. Intents sent in that
    time are either applied or rolled back with a message, never left
    hanging.
  - A refresh mid-session restores the hand, the seat and the view.
    Zoom and pan are kept in localStorage, wrapped in try/catch.
  - Two people dragging the same piece resolve without either seeing a
    glitch.
  - A dropped participant's held pieces are released 10 seconds after
    their socket closes, not at once, so that a blip does not drop a
    card in mid-drag. If the participant reconnects within the 10
    seconds, they keep their hold.
  - Error pages: an unknown room code, a closed room, a full room, a
    server error, and a refused socket. Each says what happened and what
    to do next.

Update this plan's status table. Commit.
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

**Status: Not started.** Hosting is decided: a MacBook on the local
network, served with `scripts/deploy.sh`. Read the prompt's first item as
"make `scripts/deploy.sh` the documented way to serve a session, with every
environment variable in .env.example and the README". Deploying to Fly.io
or Render is set aside until the author asks for it.

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

## 17. Open rooms and activities

**Status: Done (PR #18).** Built: the optional facilitator
seat, the open 20-person sandbox room (`sandbox/games/open_room/`), and
activities (sign-up, scoped zones and buttons, several at once, ending).
Ending an activity removes its zones and pieces rather than returning them
to the kit. Added on 2026-10-31 at the author's
direction, after Prompt 10's server side was built for a room that is one
exercise. Read CLAUDE.md's "Rooms and activities" first.

**Merging this step's pull request fires the daily routine.** The routine's
own stored order is 10, 12, 11, 13, 14, 15, 16 and does not name Prompt 17,
so before this is merged the author must change the routine to do Prompt 17
first (and, until then, to leave pull request #16 alone: it has had the
routine's marker line removed so the routine does not touch it). After this
merges, pull request #16 is rebased onto it and Prompt 10 resumes as the
Value Cards activity.

```text
Read CLAUDE.md ("Rooms and activities", "Game definitions", "Who may move
what"), sandbox/web/rooms.py, sandbox/web/live.py and sandbox/games/. Then:

ROOM
  A room is no longer created for a game. /start makes an open room, with
  a free table and a kit: the 36 value cards (content/decks/value-cards/,
  face down in a deck zone), dice, cubes, meeples and tokens. Up to 30
  people can be seated. Nobody is the facilitator by default, the creator
  included: the creator is an ordinary player.
  The facilitator is an optional admin seat. /join and /start offer "Join
  as facilitator", and every room has a "Become facilitator" button for
  anyone sitting there. One holder at a time; the holder may hand it back.
  Nothing in any activity requires it. Existing "facilitator only" rules
  apply to whoever holds it, and are unavailable when nobody does.

ACTIVITIES
  A game definition is an activity. A room's toolbar lists the activities
  it can start. "Start <activity>" opens a sign-up: anyone may add
  themselves until `players.max` have, and the facilitator, if there is
  one, may choose the players instead. When `players.min` have signed up
  the activity starts: its zones are made for those seats, its setup steps
  run, and its macros become buttons for them. An activity belongs to its
  players; everyone else keeps using the sandbox. Several activities, or
  several of the same one, run in a room at once, and each activity's
  zones and macros are scoped to its own players. Ending an activity
  returns its pieces to the sandbox kit.
  Move per_seat zones, setup, deal and the other steps to run per
  activity instance. Keep the escape hatch's shape.

KEEP, DO NOT REDO
  The generic swap operations and owner_moves_only zones from pull request
  #16 are model work and stay. The room, seat and snapshot code changes.

Tests: an open room seats 20; nobody is facilitator by default; becoming
and handing back the facilitator seat; starting an activity with the right
number of volunteers; two activities at once do not touch each other's
zones; the sandbox is unaffected. validate-games passes, and the live
tests and the Playwright suite pass. Update this plan's status table.
Commit.
```

---

## How to run the series well

One prompt, one session, one commit. If an agent drifts into the next prompt's territory, stop it — the boundaries are what keep the codebase coherent.

Prompt 4 is the one to read carefully before accepting. Ask the agent to walk you through `project()` line by line and to show you the Hypothesis properties it wrote. Everything downstream — private hands, deliberate reveals, the spectator view, the exports — is that one function being correct.

Prompts 10 and 11 depend on your written rules and on the content/exercises/*/*.csv files being filled in first - the CSV carries the cards or roles themselves, the pasted rules carry everything about how they're used. Before sending either, read your rules as a stranger would and check they answer: how many people, what each person holds, what a legal move is, who may see what and when, how a round ends, and what the facilitator decides versus what the table decides. Anything they don't answer, the agent will answer for you.

After Prompt 9, ask what it would take to add a third exercise. If the answer involves writing Python outside `sandbox/games/`, the definition format isn't finished, and it is cheap to fix there and expensive to fix later.
