#!/bin/bash
# Serve the Ethics Sandbox to anyone on the internet through a Cloudflare
# tunnel, from WSL on a Windows desktop (or any Linux or Mac).
#
#   scripts/serve-tunnel.sh                 open a tunnel, then run deploy.sh
#                                           with its address
#   scripts/serve-tunnel.sh --skip-checks   any other option is passed to
#                                           deploy.sh
#   scripts/serve-tunnel.sh --set-up-named-tunnel
#                                           store a named tunnel's address and
#                                           token, so every start uses them
#   scripts/serve-tunnel.sh --quick         a quick tunnel even when a named
#                                           tunnel is set up
#   PORT=9000 scripts/serve-tunnel.sh       serve on another port
#
# With a named tunnel set up (.sandbox-tunnel-url and .sandbox-tunnel-token,
# see "Serving it publicly" in README.md) the address is the same every time.
# Without one, a quick tunnel needs no Cloudflare account or domain, and its
# address (https://<random words>.trycloudflare.com) is new every time this
# starts. Ctrl-C stops both the server and the tunnel.

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
PORT="${PORT:-8000}"
export PORT

URL_FILE="$PROJECT_ROOT/.sandbox-tunnel-url"
TOKEN_FILE="$PROJECT_ROOT/.sandbox-tunnel-token"

set_up_named_tunnel() {
    echo "The address people will open, as set up in Cloudflare (for example"
    echo "https://sandbox.example.org):"
    read -r address
    address="$(printf '%s' "$address" | tr -d '[:space:]')"
    address="${address%/}"
    case "$address" in
        "") echo "No address given; nothing changed." >&2; exit 1 ;;
        http://*) echo "The address must start with https://." >&2; exit 1 ;;
        https://*) ;;
        *) address="https://$address" ;;
    esac
    echo "The tunnel's token (Cloudflare shows it when the tunnel is made; it"
    echo "is not echoed):"
    read -rs token
    echo
    token="$(printf '%s' "$token" | tr -d '[:space:]')"
    # Accept the whole "cloudflared service install <token>" line as well.
    case "$token" in
        *cloudflared*serviceinstall*) token="${token##*serviceinstall}" ;;
    esac
    if [ -z "$token" ]; then
        echo "No token given; nothing changed." >&2
        exit 1
    fi
    printf '%s\n' "$address" > "$URL_FILE"
    (umask 077; printf '%s' "$token" > "$TOKEN_FILE")
    echo "Saved $URL_FILE and $TOKEN_FILE."
    echo "In Cloudflare, the tunnel's public hostname must point to http://localhost:$PORT."
}

QUICK=0
PASS=()
for argument in "$@"; do
    case "$argument" in
        -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
        --set-up-named-tunnel) set_up_named_tunnel; exit 0 ;;
        --quick) QUICK=1 ;;
        *) PASS+=("$argument") ;;
    esac
done

if ! command -v cloudflared >/dev/null 2>&1; then
    echo "Missing 'cloudflared'. See \"Serving it publicly\" in README.md to install it." >&2
    exit 1
fi

NAMED=0
if [ "$QUICK" -eq 0 ] && { [ -s "$URL_FILE" ] || [ -s "$TOKEN_FILE" ]; }; then
    if [ ! -s "$URL_FILE" ] || [ ! -s "$TOKEN_FILE" ]; then
        echo "A named tunnel needs both $URL_FILE and $TOKEN_FILE." >&2
        echo "Run scripts/serve-tunnel.sh --set-up-named-tunnel, or --quick for a quick tunnel." >&2
        exit 1
    fi
    NAMED=1
fi

LOG="$(mktemp -t sandbox-tunnel.XXXXXX)"
PIDFILE="$(mktemp -u -t sandbox-tunnel-pid.XXXXXX)"
TUNNEL_PID=""

stop_tunnel() {
    if [ -n "$TUNNEL_PID" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        kill "$TUNNEL_PID" 2>/dev/null || true
        wait "$TUNNEL_PID" 2>/dev/null || true
    fi
    rm -f "$LOG" "$PIDFILE"
}
trap stop_tunnel EXIT
trap 'exit 130' INT TERM

if [ "$NAMED" -eq 1 ]; then
    TUNNEL_URL="$(tr -d '[:space:]' < "$URL_FILE")"
    TUNNEL_URL="${TUNNEL_URL%/}"
    printf '\n==> %s\n' "Opening the named Cloudflare tunnel for $TUNNEL_URL"
    # The token is read from its file, so it never appears in a process list.
    # cloudflared writes the pid file once it has a connection to Cloudflare.
    cloudflared tunnel --no-autoupdate run --token-file "$TOKEN_FILE" \
        --pidfile "$PIDFILE" >"$LOG" 2>&1 &
    TUNNEL_PID=$!
else
    printf '\n==> %s\n' "Opening a Cloudflare quick tunnel to port $PORT"
    cloudflared tunnel --no-autoupdate --url "http://localhost:$PORT" >"$LOG" 2>&1 &
    TUNNEL_PID=$!
    TUNNEL_URL=""
fi

waited=0
until { [ "$NAMED" -eq 1 ] && [ -s "$PIDFILE" ]; } || { [ "$NAMED" -eq 0 ] && [ -n "$TUNNEL_URL" ]; }; do
    if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo "cloudflared stopped before connecting. Its output:" >&2
        cat "$LOG" >&2
        exit 1
    fi
    if [ "$waited" -ge 60 ]; then
        echo "cloudflared did not connect within 30 seconds. Its output:" >&2
        cat "$LOG" >&2
        exit 1
    fi
    if [ "$NAMED" -eq 0 ]; then
        TUNNEL_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -n 1 || true)"
    fi
    sleep 0.5
    waited=$((waited + 1))
done

echo "Tunnel address: $TUNNEL_URL"
if [ "$NAMED" -eq 1 ]; then
    echo "In Cloudflare, its public hostname must point to http://localhost:$PORT."
else
    echo "It can take a minute before the address answers."
fi

# Every invite link is built from this. deploy.sh prints its own local
# addresses as well; the tunnel address is the one to share.
export SANDBOX_PUBLIC_URL="$TUNNEL_URL"
status=0
scripts/deploy.sh ${PASS[@]+"${PASS[@]}"} || status=$?

echo
if [ "$NAMED" -eq 1 ]; then
    echo "The server stopped. $TUNNEL_URL answers again when this script is next started."
else
    echo "The server stopped. The tunnel address $TUNNEL_URL no longer works."
fi
exit "$status"
