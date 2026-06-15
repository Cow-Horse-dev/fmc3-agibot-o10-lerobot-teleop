#!/usr/bin/env bash
# Machine-A: ROS2 policy node (GPU host, no hardware).
set -euo pipefail

ARM_HAND_TELEOP_PYTHON="${ARM_HAND_TELEOP_PYTHON:-$HOME/miniconda3/envs/arm-hand-teleop-pi0/bin/python}"

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

fps="${ARM_HAND_TELEOP_ASYNC_FPS:-15}"

# ROS2 environment (must match machine B).
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
# RTC (real-time chunking) toggles — same vars the gRPC async_rtc wrapper exports.
export ARM_HAND_TELEOP_RTC_ENABLED="${ARM_HAND_TELEOP_RTC_ENABLED:-1}"
export ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON="${ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON:-10}"
export ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT="${ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT:-10.0}"
export ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE="${ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE:-EXP}"
source /opt/ros/jazzy/setup.bash
# shellcheck disable=SC1091
source "$arm_hand_teleop_repo_root/ros2_ws/install/setup.bash"

"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" ros2_policy_node \
  --yaml "$arm_hand_teleop_repo_root/configs/dual_arm/o10_dual_infer.yaml" \
  --fps "$fps" \
  "$@"
