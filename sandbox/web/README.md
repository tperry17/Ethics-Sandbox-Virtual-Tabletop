FastAPI application, routes, and WebSocket hub.

## Debrief, replay and reflection (Prompt 13)

- `debrief.py` - `/t/{code}/debrief[/{activity_id}]`, `/t/{code}/class/{class_id}/debrief`,
  the facilitator's open/notes/settings posts, `/t/{code}/replay` (and its
  `frame`), `/t/{code}/reflect`. Reads the log; draws what each exercise's
  `debrief.py` (in `sandbox/games/`) returns.
- `replay.py` - rebuilds a table from the event log, read-only.
- `record.py` - the export (JSON, CSV zip), anonymising, and the data dictionary.
- `deps.py` - `get_session`, shared with the routers.
