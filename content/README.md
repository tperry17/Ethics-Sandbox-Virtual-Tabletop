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
pages. Add a row here (with a new `slug`) and matching rows in the files
below to add a new exercise to the site without touching any template.

`site/exercise_session_shape.csv`, `exercise_tensions.csv`,
`exercise_facilitator_notes.csv`, `exercise_preview_zones.csv`,
`exercise_preview_cards.csv` - each holds the repeating list items for the
exercise detail page (the numbered "what you'll be doing" steps, the
tensions it surfaces, facilitator notes, and the table preview), one row
per item, keyed by the same `slug` used in `exercises.csv`. To add, remove,
or reorder an item, add, remove, or reorder its row - the order rows appear
in the file is the order they appear on the page.

## Exercise content

Each exercise's game content - its deck, its roles, its facilitation
prompts, and what its buttons say - lives under `exercises/<exercise>/`,
and the exercise's game definition (`sandbox/games/<exercise>/game.yaml`)
names the files it reads.

`decks/value-cards/cards.csv` and the Democracy Simulation's
`roles.csv`, `jobs.csv` and `features.csv` are not read yet. Their
exercises get game definitions in later steps of the build plan
(`docs/BUILD-PLAN.md`, prompts 10 and 11), which will read exactly these
files. Fill them in as spreadsheets ahead of that work.

The Democracy Simulation's three files come from the author's "role
cards" Google Sheet. `roles.csv` has one row per card (80 in all: cards
1-20 for each city and phase), with yes/no columns for whether the holder
lives by the river, has heard the rumour, or sits on the council.
`jobs.csv` holds the knowledge and interest text for each job in each
phase. `features.csv` holds the extra line that the river, rumour and
council marks add to a card.

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
