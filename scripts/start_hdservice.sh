#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HDW_DIR="$REPO_ROOT/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64"
LOG_DIR="${HD_LOG_DIR:-$REPO_ROOT/logs}"
LOG_FILE="${HD_LOG_FILE:-$LOG_DIR/hdservice.log}"

export HD_UDP_TARGET="${HD_UDP_TARGET:-127.0.0.1:5555}"

if [[ "${HD_BACKGROUND:-0}" == "1" ]]; then
  mkdir -p "$LOG_DIR"
  nohup "$HDW_DIR/start_hdservice.sh" "$@" >"$LOG_FILE" 2>&1 &
  HD_PID=$!
  sleep 1

  if kill -0 "$HD_PID" 2>/dev/null; then
    echo "HDService started in background. PID: $HD_PID"
    echo "HDService log: $LOG_FILE"
  else
    echo "HDService exited quickly. Recent log:"
    tail -n 40 "$LOG_FILE" || true
  fi
  exit 0
fi

exec "$HDW_DIR/start_hdservice.sh" "$@"
