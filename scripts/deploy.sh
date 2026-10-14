#!/bin/bash
# Serve the Ethics Sandbox from this Mac to everyone on the same network.
#
#   scripts/deploy.sh                 checks, build, migrate, serve on port 8000
#   scripts/deploy.sh --skip-checks   skip Ruff, mypy, and pytest
#   PORT=9000 scripts/deploy.sh       serve on another port
#
# Unlike `uv run dev`, this serves without --reload and keeps its own database
# (ethics-sandbox-live.db) and cookie secret (.sandbox-secret), so a restart
# keeps every room and every participant's seat. Written for macOS's bash 3.2.

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
PORT="${PORT:-8000}"
RUN_CHECKS=1

for arg in "$@"; do
    case "$arg" in
        --skip-checks) RUN_CHECKS=0 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
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

require uv "brew install uv"
require npm "brew install node"

case "$PROJECT_ROOT" in
    *"Google Drive"*|*GoogleDrive*|*CloudStorage*)
        echo "Warning: this folder is inside a synced cloud drive ($PROJECT_ROOT)." >&2
        echo "Syncing .venv, node_modules, and the live SQLite database can corrupt them." >&2
        echo "Move the project to a local folder such as ~/Code before relying on it." >&2
        ;;
esac

step "Installing Python and client dependencies"
uv sync --frozen
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

step "Serving"
echo "On this Mac:          http://localhost:$PORT"
if [ -n "$LAN_IP" ]; then
    echo "On the same network:  http://$LAN_IP:$PORT"
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
