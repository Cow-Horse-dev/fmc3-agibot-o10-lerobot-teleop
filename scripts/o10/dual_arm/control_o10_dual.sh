#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

existing_control_pid="$(
  pgrep -f \
    "$arm_hand_teleop_repo_root/run_lerobot_play.py control --config_path $arm_hand_teleop_repo_root/configs/dual_arm/o10_dual_control.yaml" \
    | head -n 1 || true
)"

if [ -n "$existing_control_pid" ]; then
  echo "双臂 control 已在运行中，PID: $existing_control_pid" >&2
  echo "如需重启，请先执行: kill $existing_control_pid" >&2
  exit 1
fi

for required_can_interface in can0 can1; do
  if ! ip link show "$required_can_interface" >/dev/null 2>&1; then
    echo "缺少双臂控制所需 CAN 接口: $required_can_interface" >&2
    echo "当前 CAN 接口:" >&2
    ip -brief link | grep -E '(^|[[:space:]])can[0-9]+' >&2 || echo "  未发现 can 接口" >&2
    echo "请先确认左/右臂 USB-CAN 都已连接，并把 $required_can_interface 拉起来后再启动。" >&2
    exit 1
  fi
done

# 启动双臂实时控制。
# 额外参数会继续透传给 Python 命令。
"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" control \
  --config_path "$arm_hand_teleop_repo_root/configs/dual_arm/o10_dual_control.yaml" \
  "$@"
