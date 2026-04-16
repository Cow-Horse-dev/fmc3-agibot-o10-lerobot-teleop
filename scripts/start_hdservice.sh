#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common_env.sh"

cd "$arm_hand_teleop_repo_root"

# 手套数据转发到本机 5555。
export HD_UDP_TARGET=127.0.0.1:5555

# 如果传入 --background，就后台运行并把日志写到 logs/hdservice.log。
if [ $# -gt 0 ] && [ "$1" = "--background" ]; then
  shift
  mkdir -p "$arm_hand_teleop_repo_root/logs"
  nohup "$arm_hand_teleop_repo_root/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64/start_hdservice.sh" "$@" \
    >"$arm_hand_teleop_repo_root/logs/hdservice.log" 2>&1 &
  echo "HDService started in background"
  echo "log: $arm_hand_teleop_repo_root/logs/hdservice.log"
  exit 0
fi

# 默认前台运行，方便直接看输出。
exec "$arm_hand_teleop_repo_root/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64/start_hdservice.sh" "$@"
