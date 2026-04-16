#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common_env.sh"

cd "$arm_hand_teleop_repo_root"

# 先停服务，再重新拉起。
"$arm_hand_teleop_repo_root/scripts/stop_hdservice.sh" || true
sleep 1
"$arm_hand_teleop_repo_root/scripts/start_hdservice.sh" "$@"
