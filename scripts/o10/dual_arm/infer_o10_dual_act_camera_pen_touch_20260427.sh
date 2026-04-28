#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

# ACT 双臂推理：右手拿相机，左手拿笔触碰。
# 额外参数会继续透传给 Python 命令。
"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" infer \
  --yaml "$arm_hand_teleop_repo_root/configs/dual_arm/models/act_right_hand_camera_left_hand_pen_touch_20260427.yaml" \
  "$@"
