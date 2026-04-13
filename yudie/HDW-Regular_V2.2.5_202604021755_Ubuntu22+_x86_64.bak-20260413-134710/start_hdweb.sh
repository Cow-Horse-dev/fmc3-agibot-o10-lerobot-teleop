#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$SCRIPT_DIR/HDWebClient"
PORT="${HDWEB_PORT:-8088}"
SERVER_PORT="${HD_WS_PORT:-7789}"
SERVER_IP="${HD_SERVER_IP:-$(hostname -I | awk '{print $1}')}"
CONFIG_FILE="$WEB_DIR/server-config.json"

if [ -z "$SERVER_IP" ]; then
  echo "Unable to detect local IP. Set HD_SERVER_IP and rerun." >&2
  exit 1
fi

cat > "$CONFIG_FILE" <<EOF
{
  "serverUrl": "ws://$SERVER_IP:$SERVER_PORT"
}
EOF

echo "HDWebClient serverUrl set to ws://$SERVER_IP:$SERVER_PORT"
echo "Open http://$SERVER_IP:$PORT/ in your browser"

if ss -ltnp 2>/dev/null | grep -q ":$PORT "; then
  echo "HDWebClient HTTP server is already running on port $PORT."
  echo "Open http://$SERVER_IP:$PORT/ directly."
  exit 0
fi

cd "$WEB_DIR"
exec python3 -m http.server "$PORT"
