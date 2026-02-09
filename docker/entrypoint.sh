#!/bin/sh
set -e

CLOUDFLARED_PID=""

cleanup() {
    if [ -n "$CLOUDFLARED_PID" ]; then
        echo "Stopping cloudflared (PID $CLOUDFLARED_PID)..."
        kill "$CLOUDFLARED_PID" 2>/dev/null || true
        wait "$CLOUDFLARED_PID" 2>/dev/null || true
    fi
    exit 0
}

trap cleanup TERM INT

# Start cloudflared if TUNNEL_TOKEN is set
if [ -n "$TUNNEL_TOKEN" ]; then
    echo "Starting cloudflared tunnel..."
    cloudflared tunnel run --token "$TUNNEL_TOKEN" &
    CLOUDFLARED_PID=$!
    echo "cloudflared started (PID $CLOUDFLARED_PID)"
else
    echo "TUNNEL_TOKEN not set, skipping cloudflared (local dev mode)"
fi

# Start plurk-tools serve in foreground (admin on :8001 by default)
cd /app/tools
exec uv run plurk-tools serve --port 8000
