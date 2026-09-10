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

`site/principles.csv` - the six "Principles of engagement" cards shown on
the landing page.

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

## Templates for exercise content (not live yet)

`exercises/value-cards-trading/cards.csv` and
`exercises/democracy-simulation/roles.csv` are templates for each
exercise's actual game content - the full value-card deck, the roles in
the simulation. They are not read by the running site yet, because the
game-definition system that deals cards and assigns roles from a file like
this hasn't been built (that's a later step in the build plan). They exist
now so the content itself - the real deck, the real roles - can be filled
in and reviewed as a spreadsheet ahead of that work, rather than pasted
into a prompt as a block of text. Edit them the same way as everything
else here; when that system is built, it will read from exactly these
files.
