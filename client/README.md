The table client: the only TypeScript in the project, compiled by Vite to
`static/table/table.js`.

`src/` renders the table and moves the camera. It holds no rule, no deck,
and no face the server did not send it; doing something to a piece is an
intent, and the server decides what happened. See the table client section
of `CLAUDE.md` for the module map and the frame budget.

`tests/` are Playwright specs. Most of them drive the client from the
recorded session in `src/recording.ts` by way of `/table-preview`, so
rendering is tested without a room, a socket, or a database.
