#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common_env.sh"

repo_root="$arm_hand_teleop_repo_root"
python_bin="$arm_hand_teleop_python_bin"
web_dir="$repo_root/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64/HDWebClient"
port="${HDWEB_PORT:-8088}"
server_port="${HD_WS_PORT:-7789}"
server_ip="${HD_SERVER_IP:-$(hostname -I | awk '{print $1}')}"
server_url="ws://${server_ip}:${server_port}"

cd "$repo_root"

if [ -z "$server_ip" ]; then
  echo "Unable to detect local IP. Set HD_SERVER_IP and rerun." >&2
  exit 1
fi

if ss -ltnp 2>/dev/null | grep -q ":${port} "; then
  echo "HDWebClient HTTP server is already running on port ${port}."
  echo "Open http://${server_ip}:${port}/ directly."
  exit 0
fi

exec "$python_bin" \
  "$repo_root/scripts/serve_hdweb.py" \
  --web-dir "$web_dir" \
  --port "$port" \
  --server-url "$server_url" \
  "$@"
