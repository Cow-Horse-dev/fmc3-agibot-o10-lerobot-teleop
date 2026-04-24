#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

# 先停服务，再重新拉起。
"$arm_hand_teleop_repo_root/scripts/services/stop_hdservice.sh" || true
sleep 1
"$arm_hand_teleop_repo_root/scripts/services/start_hdservice.sh" "$@"
