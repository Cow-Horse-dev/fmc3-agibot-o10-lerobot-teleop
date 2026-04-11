#!/usr/bin/env bash
set -euo pipefail

# 进入项目根目录。
cd ~/workspace/arm-hand-teleop

# 启动 HDWeb 页面。
exec ~/workspace/arm-hand-teleop/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64/start_hdweb.sh "$@"
