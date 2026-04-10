#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

"$REPO_ROOT/scripts/stop_hdservice.sh" || true
sleep 1
exec "$REPO_ROOT/scripts/start_hdservice.sh" "$@"
