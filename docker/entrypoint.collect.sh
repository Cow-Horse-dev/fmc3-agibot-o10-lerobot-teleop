#!/usr/bin/env bash
set -eo pipefail

# 激活 conda 环境
eval "$(/opt/miniconda3/bin/conda shell.bash hook)"
conda activate arm-hand-teleop

# ROS setup
set +u
source "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"
set -u

cd ~/workspace/arm-hand-teleop 2>/dev/null || true
exec "$@"
