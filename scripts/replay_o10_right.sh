#!/usr/bin/env bash
set -euo pipefail

# 进入项目根目录。
cd ~/workspace/arm-hand-teleop

# 回放右手数据集。
# 额外参数会继续透传给 Python 命令。
~/miniconda3/envs/arm-hand-teleop/bin/python \
  ~/workspace/arm-hand-teleop/run_lerobot_play.py replay \
  --yaml ~/workspace/arm-hand-teleop/configs/o10_right_replay.yaml \
  "$@"
