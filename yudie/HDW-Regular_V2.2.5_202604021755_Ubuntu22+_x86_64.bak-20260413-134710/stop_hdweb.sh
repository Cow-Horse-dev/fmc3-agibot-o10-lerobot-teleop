#!/usr/bin/env bash
set -euo pipefail

if pgrep -f 'python3 -m http.server 8088' >/dev/null 2>&1; then
  pkill -f 'python3 -m http.server 8088'
  echo "HDWebClient HTTP server stopped."
else
  echo "HDWebClient HTTP server is not running on port 8088."
fi
