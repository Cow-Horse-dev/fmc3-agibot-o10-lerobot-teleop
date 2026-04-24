#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

# 启动右手实时控制。
# 额外参数会继续透传给 Python 命令。
"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" control \
  --config_path "$arm_hand_teleop_repo_root/configs/right_arm/o10_right_control.yaml" \
  "$@"
