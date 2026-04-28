#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

# 启动本项目适配过的异步策略服务端。
# PI0/PI0.5 LoRA adapter 推理需要用这个入口，不要直接用 python -m lerobot.async_inference.policy_server。
"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" async_policy_server \
  "$@"
