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

`scripts/deploy.sh` runs the checks, builds the client, migrates its own database, and serves the tabletop on port 8000 to everyone on the same network. It prints the address participants should open. Pass `--skip-checks` to skip Ruff, mypy, and pytest, or set `PORT` to use another port.
