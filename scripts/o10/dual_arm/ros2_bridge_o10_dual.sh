#!/usr/bin/env bash
# Machine-B: ROS2 robot bridge (owns the O10 dual-arm hardware).
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

model_path="${ARM_HAND_TELEOP_PI05_MODEL_PATH:-$HOME/workspace/mymodels/qiuzhi_agibot/camera_pen_touch_clean_del_52_376/pi0/pi05_camera_pen_touch_clean_del_52_376_selected/120000/pretrained_model}"
policy="${ARM_HAND_TELEOP_POLICY:-pi05}"
fps="${ARM_HAND_TELEOP_ASYNC_FPS:-15}"
actions_per_chunk="${ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK:-50}"
chunk_size_threshold="${ARM_HAND_TELEOP_ASYNC_CHUNK_SIZE_THRESHOLD:-0.8}"

# ROS2 environment (must match the policy host on machine A).
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
source /opt/ros/jazzy/setup.bash
# shellcheck disable=SC1091
source "$arm_hand_teleop_repo_root/ros2_ws/install/setup.bash"

# Pre-flight: refuse to start a duplicate bridge (would fight over CAN buses).
if pgrep -f "ros2_robot_bridge" >/dev/null 2>&1; then
  echo "ros2_robot_bridge already running; aborting." >&2
  exit 1
fi

"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" ros2_robot_bridge \
  --yaml "$arm_hand_teleop_repo_root/configs/dual_arm/o10_dual_infer.yaml" \
  --policy "$policy" \
  --model_path "$model_path" \
  --fps "$fps" \
  --actions_per_chunk "$actions_per_chunk" \
  --chunk_size_threshold "$chunk_size_threshold" \
  "$@"
