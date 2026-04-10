#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

exec "$REPO_ROOT/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64/stop_hdweb.sh" "$@"
