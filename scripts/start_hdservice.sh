#!/usr/bin/env bash
set -euo pipefail

# 进入项目根目录。
cd ~/workspace/arm-hand-teleop

# 手套数据转发到本机 5555。
export HD_UDP_TARGET=127.0.0.1:5555

# 如果传入 --background，就后台运行并把日志写到 logs/hdservice.log。
if [ $# -gt 0 ] && [ "$1" = "--background" ]; then
  shift
  mkdir -p ~/workspace/arm-hand-teleop/logs
  nohup ~/workspace/arm-hand-teleop/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64/start_hdservice.sh "$@" \
    >~/workspace/arm-hand-teleop/logs/hdservice.log 2>&1 &
  echo "HDService started in background"
  echo "log: ~/workspace/arm-hand-teleop/logs/hdservice.log"
  exit 0
fi

# 默认前台运行，方便直接看输出。
exec ~/workspace/arm-hand-teleop/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64/start_hdservice.sh "$@"
