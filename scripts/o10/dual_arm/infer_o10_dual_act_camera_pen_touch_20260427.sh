#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

for required_can_interface in can0 can1; do
  if ! ip link show "$required_can_interface" >/dev/null 2>&1; then
    echo "缺少双臂推理所需 CAN 接口: $required_can_interface" >&2
    echo "当前 CAN 接口:" >&2
    ip -brief link | grep -E '(^|[[:space:]])can[0-9]+' >&2 || echo "  未发现 can 接口" >&2
    echo "请先确认左/右臂 USB-CAN 都已连接，并把 $required_can_interface 拉起来后再启动。" >&2
    exit 1
  fi
done

# ACT 双臂推理：右手拿相机，左手拿笔触碰。
# 额外参数会继续透传给 Python 命令。
"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" infer \
  --yaml "$arm_hand_teleop_repo_root/configs/dual_arm/models/act_right_hand_camera_left_hand_pen_touch_20260427.yaml" \
  "$@"
