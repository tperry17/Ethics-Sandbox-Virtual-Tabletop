# Rough edges

Every known limitation and shortcut, as of Prompt 16. Nothing here is a
secret; most of it is a choice made to ship.

## Hosting

- Hosting is a Mac on the local network, one process, one worker. There is
  no staging or production, no TLS, and no way for people outside the
  network to join. Fly.io or Render is set aside until the author asks.
- Live tables are held in memory by the one process. If it stops, the table
  is restored from its last save; the last moment or two of play can be lost.
- Over plain `http`, browsers give no clipboard access, so "Copy invite
  link" selects the text and asks the person to copy it themselves.
- Without `SANDBOX_SECRET_KEY` the app uses a fixed development secret.
  `scripts/deploy.sh` always sets one; running `uvicorn` by hand does not.
- The Mac must stay awake, charged and on the same network as the tablets.

## Site

- No page has a social-preview image. The Center's seal would be the
  obvious picture, and any new use of it needs the Center's approval. Pages
  do carry titles, descriptions and Open Graph text.
- The exercise page's picture of a table is an HTML mock-up from CSV, not a
  capture of a real table.
- `/exercises` and `/about` do not exist.

## Facilitating

- No group has played the finished exercises, so the timings in
  `docs/FACILITATING.md` come from the definitions and are untested.
- Deferred from Prompt 12: a pause control, table snapshots restorable by
  the facilitator, separate "unlock all" and "recall all" controls, renaming
  seats, a read-only spectator view, and facilitator handover after 60
  seconds away.
- `uv run sandbox seed-demo` seats fake people at every seat of the
  exercise; a real browser that opens the room joins as an observer and
  cannot play a seat. It is for showing the table, not for practising on.

## Accessibility and devices

- Dragging a piece is not announced by screen readers; deals, trades,
  votes, reveals and joins are. `docs/MANUAL-CHECKS.md` lists what has been
  checked only by hand, and has not yet been run on a real iPad.
- On a phone under 600 px, the public table can be panned and zoomed but
  its pieces cannot be dragged.
- Colour is never the only way to tell seats apart, but this has been
  checked with a simulator only.
