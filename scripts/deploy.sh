#!/bin/bash
# Serve the Ethics Sandbox from this Mac to everyone on the same network.
#
#   scripts/deploy.sh                 update main, stop the old server, check,
#                                     build, migrate, serve on port 8000
#   scripts/deploy.sh --skip-checks   skip Ruff, mypy, and pytest
#   scripts/deploy.sh --no-pull       serve the checkout as it is, without
#                                     switching to and updating main
#   PORT=9000 scripts/deploy.sh       serve on another port
#
# Unlike `uv run dev`, this serves without --reload and keeps its own database
# (ethics-sandbox-live.db) and cookie secret (.sandbox-secret), so a restart
# keeps every room and every participant's seat. Written for macOS's bash 3.2.

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd -P)"
PORT="${PORT:-8000}"
RUN_CHECKS=1
PULL=1

for arg in "$@"; do
    case "$arg" in
        --skip-checks) RUN_CHECKS=0 ;;
        --no-pull) PULL=0 ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

step() { printf '\n==> %s\n' "$1"; }

require() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing '$1'. Install it with: $2" >&2
        exit 1
    fi
}

# The working directory of a process, or nothing if it cannot be read.
process_cwd() {
    if [ -r "/proc/$1/cwd" ]; then
        readlink "/proc/$1/cwd" 2>/dev/null || true
    else
        lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
    fi
}

# PIDs of this project's servers and watchers: `uv run dev`, its Uvicorn and
# Vite children, an earlier run of this script, and anything else started
# here that is listening on $PORT.
project_pids() {
    {
        pgrep -f 'uvicorn sandbox\.web\.app:app' || true
        pgrep -f 'vite build --watch' || true
        pgrep -f '\.venv/bin/dev' || true
        if command -v lsof >/dev/null 2>&1; then
            lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true
        fi
    } | sort -un | while read -r pid; do
        if [ -n "$pid" ] && [ "$pid" != "$$" ] && [ "$(process_cwd "$pid")" = "$PROJECT_ROOT" ]; then
            echo "$pid"
        fi
    done
}

stop_running_servers() {
    local pids pid waited
    pids="$(project_pids)"
    if [ -z "$pids" ]; then
        echo "Nothing running."
        return
    fi
    for pid in $pids; do
        echo "Stopping $pid: $(ps -o command= -p "$pid" 2>/dev/null || true)"
        kill "$pid" 2>/dev/null || true
    done
    waited=0
    while [ -n "$(project_pids)" ] && [ "$waited" -lt 10 ]; do
        sleep 0.5
        waited=$((waited + 1))
    done
    for pid in $(project_pids); do
        kill -9 "$pid" 2>/dev/null || true
    done
}

require git "xcode-select --install"
require uv "brew install uv"
require npm "brew install node"

if [ "$PULL" -eq 1 ] && [ -z "${SANDBOX_DEPLOY_UPDATED:-}" ]; then
    step "Updating to the latest main"
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
        echo "This checkout has uncommitted changes, so it was not switched to main:" >&2
        git status --short --untracked-files=no >&2
        echo "Commit or stash them, or run with --no-pull to serve the checkout as it is." >&2
        exit 1
    fi
    git fetch origin main
    git checkout main
    git merge --ff-only origin/main
    # Run the version of this script that just arrived, not the one in memory.
    SANDBOX_DEPLOY_UPDATED=1 exec "$PROJECT_ROOT/scripts/deploy.sh" "$@"
fi

case "$PROJECT_ROOT" in
    *"Google Drive"*|*GoogleDrive*|*CloudStorage*)
        echo "Warning: this folder is inside a synced cloud drive ($PROJECT_ROOT)." >&2
        echo "Syncing .venv, node_modules, and the live SQLite database can corrupt them." >&2
        echo "Move the project to a local folder such as ~/Code before relying on it." >&2
        ;;
esac

step "Stopping servers already running from this folder"
stop_running_servers

step "Installing Python and client dependencies"
# A virtualenv activated in this terminal, such as one from the project's old
# location, must not stand in for this project's own .venv.
unset VIRTUAL_ENV
# A .venv copied or moved from another folder keeps that folder's paths in its
# scripts and fails at the first `uv run`. Rebuild it rather than reuse it.
if [ -d .venv ] && ! { .venv/bin/python -c '' && .venv/bin/pytest --version; } >/dev/null 2>&1; then
    echo "The .venv here was built for another folder; rebuilding it."
    rm -rf .venv
fi
uv sync --frozen
# npm ci always replaces node_modules, so a copied one is never reused.
npm ci --no-audit --no-fund

if [ "$RUN_CHECKS" -eq 1 ]; then
    step "Running Ruff, mypy, and pytest"
    uv run ruff check .
    uv run mypy sandbox tests
    uv run pytest -q
fi

step "Building the table client"
npm run build

step "Preparing the cookie secret and database"
SECRET_FILE="$PROJECT_ROOT/.sandbox-secret"
if [ -z "${SANDBOX_SECRET_KEY:-}" ]; then
    if [ ! -s "$SECRET_FILE" ]; then
        (umask 077; uv run python -c "import secrets; print(secrets.token_urlsafe(48))" > "$SECRET_FILE")
        echo "Created $SECRET_FILE"
    fi
    SANDBOX_SECRET_KEY="$(cat "$SECRET_FILE")"
fi
export SANDBOX_SECRET_KEY
export DATABASE_URL="${DATABASE_URL:-sqlite:///$PROJECT_ROOT/ethics-sandbox-live.db}"
uv run alembic upgrade head

LAN_IP=""
if command -v ipconfig >/dev/null 2>&1; then
    LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
fi

# Every link the app shares is built from this, so it must be the address other
# devices can reach, never localhost. Set SANDBOX_PUBLIC_URL to override it.
if [ -z "${SANDBOX_PUBLIC_URL:-}" ] && [ -n "$LAN_IP" ]; then
    SANDBOX_PUBLIC_URL="http://$LAN_IP:$PORT"
fi
export SANDBOX_PUBLIC_URL="${SANDBOX_PUBLIC_URL:-}"

step "Serving"
echo "On this Mac:          http://localhost:$PORT"
if [ -n "$LAN_IP" ]; then
    echo "On the same network:  http://$LAN_IP:$PORT"
    echo "Check from a tablet:  http://$LAN_IP:$PORT/health"
fi
echo "If macOS asks whether Python may accept incoming connections, choose Allow."
echo "Press Ctrl-C to stop."

# One worker: the WebSocket hub holds each room's live state in this process.
SERVER=(uv run uvicorn sandbox.web.app:app --host 0.0.0.0 --port "$PORT" --workers 1)
if command -v caffeinate >/dev/null 2>&1; then
    # Keep the Mac awake while it is serving a session.
    exec caffeinate -i "${SERVER[@]}"
fi
exec "${SERVER[@]}"
