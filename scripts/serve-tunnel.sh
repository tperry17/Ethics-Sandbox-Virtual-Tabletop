#!/bin/bash
# Serve the Ethics Sandbox to anyone on the internet through a Cloudflare
# quick tunnel, from WSL on a Windows desktop (or any Linux or Mac).
#
#   scripts/serve-tunnel.sh                 open a tunnel, then run deploy.sh
#                                           with its address
#   scripts/serve-tunnel.sh --skip-checks   any option is passed to deploy.sh
#   PORT=9000 scripts/serve-tunnel.sh       serve on another port
#
# A quick tunnel needs no Cloudflare account or domain. Its address
# (https://<random words>.trycloudflare.com) is new every time this starts,
# so share the links printed below each session. Ctrl-C stops both the server
# and the tunnel.

set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
export PORT

case "${1:-}" in
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
esac

if ! command -v cloudflared >/dev/null 2>&1; then
    echo "Missing 'cloudflared'. See \"Serving it publicly\" in README.md to install it." >&2
    exit 1
fi

LOG="$(mktemp -t sandbox-tunnel.XXXXXX)"
TUNNEL_PID=""

stop_tunnel() {
    if [ -n "$TUNNEL_PID" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        kill "$TUNNEL_PID" 2>/dev/null || true
        wait "$TUNNEL_PID" 2>/dev/null || true
    fi
    rm -f "$LOG"
}
trap stop_tunnel EXIT
trap 'exit 130' INT TERM

printf '\n==> %s\n' "Opening a Cloudflare quick tunnel to port $PORT"
cloudflared tunnel --no-autoupdate --url "http://localhost:$PORT" >"$LOG" 2>&1 &
TUNNEL_PID=$!

TUNNEL_URL=""
waited=0
while [ -z "$TUNNEL_URL" ]; do
    if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo "cloudflared stopped before giving an address. Its output:" >&2
        cat "$LOG" >&2
        exit 1
    fi
    if [ "$waited" -ge 60 ]; then
        echo "cloudflared gave no address within 30 seconds. Its output:" >&2
        cat "$LOG" >&2
        exit 1
    fi
    TUNNEL_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -n 1 || true)"
    if [ -z "$TUNNEL_URL" ]; then
        sleep 0.5
        waited=$((waited + 1))
    fi
done

echo "Tunnel address: $TUNNEL_URL"
echo "It can take a minute before the address answers."

# Every invite link is built from this. deploy.sh prints its own local
# addresses as well; the tunnel address is the one to share.
export SANDBOX_PUBLIC_URL="$TUNNEL_URL"
status=0
scripts/deploy.sh "$@" || status=$?

echo
echo "The server stopped. The tunnel address $TUNNEL_URL no longer works."
exit "$status"
