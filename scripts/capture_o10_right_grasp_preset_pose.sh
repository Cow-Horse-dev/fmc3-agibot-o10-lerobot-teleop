#!/usr/bin/env bash
set -euo pipefail

# 进入项目根目录。
cd ~/workspace/arm-hand-teleop

# 先手动把 O10 右手摆到你想要的“固定抓取骨架”姿态，再执行这个脚本。
# 默认直接读取机器人手当前关节，并写入：
#   ~/workspace/arm-hand-teleop/configs/o10_right_hand_grasp_preset_pose.json
# 额外参数会继续透传给 Python 命令。
~/miniconda3/envs/arm-hand-teleop/bin/python \
  ~/workspace/arm-hand-teleop/scripts/capture_o10_hand_pose.py \
  --handedness right \
  --pose-kind grasp_preset \
  --source robot \
  --output ~/workspace/arm-hand-teleop/configs/o10_right_hand_grasp_preset_pose.json \
  "$@"
