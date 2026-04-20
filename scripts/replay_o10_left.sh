#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common_env.sh"

cd "$arm_hand_teleop_repo_root"

# 启动左手回放。
# 额外参数会继续透传给 Python 命令。
"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" replay \
  --yaml "$arm_hand_teleop_repo_root/configs/o10_left_replay.yaml" \
  "$@"
