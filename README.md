# Ethics Sandbox

A virtual tabletop for structured exercises about values, ethics, and democratic decision-making.

## Development

```sh
uv sync
npm install
uv run dev
```

Run the checks with `uv run ruff check .`, `uv run mypy sandbox tests`, `uv run pytest`, and `npm run test:e2e`.

## Running a session from a Mac

`scripts/deploy.sh` switches to the latest `main`, stops any server or watcher already running from this folder, runs the checks, builds the client, migrates its own database, and serves the tabletop on port 8000 to everyone on the same network. It prints the address participants should open. It refuses to switch branches over uncommitted changes, and rebuilds a `.venv` that was copied from another folder. Pass `--skip-checks` to skip Ruff, mypy, and pytest, `--no-pull` to serve the checkout as it is, or set `PORT` to use another port.

### Environment variables

`.env.example` lists every variable the app reads, with what each is for.
`scripts/deploy.sh` sets `SANDBOX_SECRET_KEY`, `DATABASE_URL` and
`SANDBOX_PUBLIC_URL` itself; export one before running it to override.

| Variable | Used for |
| --- | --- |
| `SANDBOX_SECRET_KEY` | Signs the identity cookie. Keep it stable between runs. |
| `DATABASE_URL` | Where tables are saved (SQLite file, or Postgres). |
| `SANDBOX_PUBLIC_URL` | The address in invite links and page metadata. |
| `PORT` | `deploy.sh` only: the port to serve on. |
| `SANDBOX_EXTRA_GAMES` | Tests only: extra game folders. |

The table runs on websockets held by one server process, with live tables
kept in that process's memory. Run a single worker (`deploy.sh` does), on a
host that keeps the process running; serverless or scale-to-zero hosting
will drop every table's connections. Hosting is the Mac on the local
network for now; Fly.io or Render, with staging and production, is set
aside until asked for.

### Serving it publicly through a Cloudflare quick tunnel

`scripts/serve-tunnel.sh` opens a Cloudflare quick tunnel to the server's
port, waits for its `https://<random words>.trycloudflare.com` address, and
runs `scripts/deploy.sh` with `SANDBOX_PUBLIC_URL` set to it, so every
invite link carries that address. It takes the same options as `deploy.sh`.
Ctrl-C stops the server and the tunnel together. It needs `cloudflared`
and no Cloudflare account or domain.

A quick tunnel's address is new every time `cloudflared` starts, so share
the new links each session. Cloudflare offers quick tunnels "for testing and
development", with no uptime guarantee and up to 200 in-flight requests.
Because the identity cookie belongs to the address it was issued on, someone
returning to a room under a new address is a new participant. That suits a
room used in one sitting; for a lasting address, use a named tunnel on a
domain of your own and set `SANDBOX_PUBLIC_URL` to it.

The machine must stay on, awake and online for the whole session, keep the
same `SANDBOX_SECRET_KEY` and database file between runs (`deploy.sh` does),
and run one copy of the server only.

On Windows, without WSL, `scripts\serve-tunnel.cmd` does the same: it runs
`scripts/serve-tunnel.ps1`, the PowerShell counterpart of `deploy.sh` and
`serve-tunnel.sh`, and serves on `127.0.0.1` only, since the tunnel is all
that needs to reach it. See `docs/FACILITATING-ON-WINDOWS.md`.

### Showing an exercise without a group

`uv run sandbox seed-demo value-cards-trading` (or
`democracy-simulation --people 9`) makes a room with fake participants and
the exercise begun, and prints its code. Open `/t/<code>` on the running
server. Use the same `DATABASE_URL` as the server.

For how to run each exercise, see `docs/FACILITATING.md`; for what does not
work yet, `docs/ROUGH-EDGES.md`.
