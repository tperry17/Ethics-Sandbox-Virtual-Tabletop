# Content

Editorial text for the site lives here as CSV files, not as Python code, so
it can be updated by editing a spreadsheet. Since this project folder is
inside Google Drive, you can open any of these files directly in Google
Sheets, Excel, or Numbers, edit it, and save it back as `.csv` (not
`.xlsx`) - Drive keeps the saved file in place. Editing in a plain text
editor works too; each file is just comma-separated rows with a header.

**The site picks up changes on the next server restart.** Content is read
once when the app starts, not on every page view. In local development
(`uv run dev`), editing a CSV under this folder triggers the same
auto-reload as editing a Python file. When the app is deployed, a fresh
deploy re-reads whatever is in these files at that moment - "we deploy" and
"it uses the latest text" are the same thing.

Keep the header row of every file exactly as it is; add, remove, or edit
rows below it. A cell with a comma in it needs to be wrapped in double
quotes - most spreadsheet apps do this for you automatically when you save.

## Live on the site today

`site/exercises.csv` - one row per exercise: title, blurb, premise, group
size, running time, and the rest of the fields on its catalog and detail
pages. The exercise page opens with the `premise`; `overview`, if filled
in, is a section under the heading in `overview_heading` (or "Premise" if
that is blank). `facilitator` is shown on the landing page's cards. Add a
row here (with a new `slug`) and matching rows in the files below to add a
new exercise to the site without touching any template.

`site/exercise_learning_outcomes.csv` - what each exercise is designed to
achieve: one row per outcome (`slug`, `id`, `title`, `text`). It is shown on
the exercise's page and is the set of outcome cards on its debrief table.

`site/help_records.csv` - the Help page's notes on records: a heading and a
paragraph per row.

`site/exercise_preview_zones.csv`, `exercise_preview_cards.csv` - the table
preview on the exercise detail page, one row per item, keyed by the same
`slug` used in `exercises.csv`, used when an exercise has no game
definition to draw from. The order rows appear in the file is the order
they appear on the page.

## Exercise content

Each exercise's game content - its deck, its roles, its facilitation
prompts, and what its buttons say - lives under `exercises/<exercise>/`,
and the exercise's game definition (`sandbox/games/<exercise>/game.yaml`)
names the files it reads.

Both exercises' definitions read these files. Leadership and Knowledge
in Popular Rule does not read its sheets directly: `role_cards.csv`, `moderator_cards.csv`,
`sheet_cards.csv` and `invitation_cards.csv` are composed from `roles.csv`,
`jobs.csv`, `features.csv`, `elite_sheets.csv` and `invitations.csv`, because
a card's back is made of several of them. **After editing any of those five,
run `uv run python sandbox/games/democracy_simulation/compose.py`** and commit
the four files it writes; a test fails until you do. `outcomes.csv` (the nine
outcomes of Scenario 2's war table) is kept for the class page, and
`prompts.csv` holds the debrief questions, each under its learning outcome.

Leadership and Knowledge in Popular Rule's three files come from the
author's "role cards" Google Sheet. `roles.csv` has one row per card (80 in all: cards
1-20 for each city and phase), with yes/no columns for whether the holder
lives by the river, has heard the rumour, or sits on the council.
`jobs.csv` holds the knowledge and interest text for each job in each
phase. `features.csv` holds the extra line that the river, rumour and
council marks add to a card. `elite_sheets.csv` holds the information
sheet each elite card comes with, and `invitations.csv` each city's
invitation for each phase. Both come from the author's four "Printouts"
Google Docs, with typos corrected (listed in `docs/BUILD-PLAN.md`, Prompt
11). Their text keeps the printouts' bold and italic as `**bold**` and
`*italic*`. A line starting `# ` is a heading, list items start `- ` or
`1. `, and a literal asterisk is written `\*`.

`decks/value-cards/cards.csv` is the Value Cards deck as printed, copied
from the "deck" sheet of the author's "values cards - the spreadsheet".
It sits under `decks/` rather than under one exercise because several
exercises will use it. `art` names the card's picture and `schwartz` the
category whose icon is printed in its corner.

A game's buttons CSV (for example `exercises/<exercise>/buttons.csv`) has
one row per button: `id` (which button; it matches the game definition),
`label`, `hint` (shown on hover), `confirm` (the question asked before a
button that clears or undoes something) and `announce` (what everyone is
told afterwards; `{name}` is whoever pressed it and `{label}` the button).
Only `id` and `label` must be filled in.

In a deck, the column the definition names as its `key` (`name` in these
files) must be unique: it identifies the card. Renaming a card is changing
its key, so rename between sessions, not during one.

Each of these CSVs has an `image` column. A card or role can be an
uploaded image instead of (or as well as) its text fields: put the image
file in that exercise's `images/` subfolder (PNG, JPG, or SVG all work),
then put its filename - just the filename, not a path - in the `image`
cell on that row. Leave `image` blank for a card that should be generated
from its text fields instead; a deck can freely mix generated and
image-based cards. See the `README.md` inside each `images/` folder.
