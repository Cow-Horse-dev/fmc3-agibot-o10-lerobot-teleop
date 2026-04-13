#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
port="${HDWEB_PORT:-8088}"

cd "$repo_root"

if pgrep -f "serve_hdweb.py --web-dir .*HDWebClient --port ${port}" >/dev/null 2>&1; then
  pkill -f "serve_hdweb.py --web-dir .*HDWebClient --port ${port}"
  echo "HDWebClient HTTP server stopped."
  exit 0
fi

if pgrep -f "python3 -m http.server ${port}" >/dev/null 2>&1; then
  pkill -f "python3 -m http.server ${port}"
  echo "Legacy HDWebClient HTTP server stopped."
  exit 0
fi

echo "HDWebClient HTTP server is not running on port ${port}."
