#!/usr/bin/env bash
set -euo pipefail

if pgrep -f '/HDService$' >/dev/null 2>&1; then
  pkill -f '/HDService$'
  echo "HDService stopped."
else
  echo "HDService is not running."
fi
