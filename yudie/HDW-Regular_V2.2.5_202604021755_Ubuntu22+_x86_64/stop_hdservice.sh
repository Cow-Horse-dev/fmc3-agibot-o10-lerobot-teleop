#!/usr/bin/env bash
set -euo pipefail

pattern='/HDService$'

if ! pgrep -f "$pattern" >/dev/null 2>&1; then
  echo "HDService is not running."
  exit 0
fi

pkill -f "$pattern" || true
sleep 1

if pgrep -f "$pattern" >/dev/null 2>&1; then
  pkill -9 -f "$pattern" || true
  sleep 1
fi

if pgrep -f "$pattern" >/dev/null 2>&1; then
  echo "Failed to stop HDService."
  exit 1
fi

echo "HDService stopped."
