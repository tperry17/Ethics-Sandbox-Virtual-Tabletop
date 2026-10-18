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

## Claiming a build-plan step

`scripts/claim-step.sh <number>` claims a step of `docs/BUILD-PLAN.md` so no one else starts it. It refuses a step that is done, waiting on the author, or already claimed, and otherwise pushes the step's branch with the step marked "Claimed", then marks it "Claimed" on `main` as well, so the status table there shows it. Only the first push to that branch succeeds, so two people claiming at once cannot both win. Open a draft pull request for the branch straight afterwards.
