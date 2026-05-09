#!/usr/bin/env bash
set -euo pipefail

ARM_HAND_TELEOP_PYTHON="${ARM_HAND_TELEOP_PYTHON:-$HOME/miniconda3/envs/arm-hand-teleop-pi0/bin/python}"

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

model_path="${ARM_HAND_TELEOP_PI05_MODEL_PATH:-$HOME/workspace/mymodels/qiuzhi_agibot/camera_pen_touch_clean_del_52_376/pi0/pi05_camera_pen_touch_clean_del_52_376_selected/120000/pretrained_model}"
server_host="${ARM_HAND_TELEOP_ASYNC_SERVER_HOST:-localhost}"
server_port="${ARM_HAND_TELEOP_ASYNC_SERVER_PORT:-8080}"
server_address="${server_host}:${server_port}"
fps="${ARM_HAND_TELEOP_ASYNC_FPS:-30}"
inference_latency="${ARM_HAND_TELEOP_ASYNC_INFERENCE_LATENCY:-0.35}"
actions_per_chunk="${ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK:-50}"
chunk_size_threshold="${ARM_HAND_TELEOP_ASYNC_CHUNK_SIZE_THRESHOLD:-0.8}"

export ARM_HAND_TELEOP_RTC_ENABLED="${ARM_HAND_TELEOP_RTC_ENABLED:-1}"
export ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON="${ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON:-10}"
export ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT="${ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT:-10.0}"
export ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE="${ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE:-EXP}"

"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" async_policy_server \
  --host "$server_host" \
  --port "$server_port" \
  --fps "$fps" \
  --inference_latency "$inference_latency" &
server_pid="$!"

cleanup() {
  if kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

sleep 2

"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" infer \
  --yaml "$arm_hand_teleop_repo_root/configs/dual_arm/o10_dual_infer.yaml" \
  --policy pi05 \
  --model_path "$model_path" \
  --async_infer \
  --fps "$fps" \
  --server_address "$server_address" \
  --actions_per_chunk "$actions_per_chunk" \
  --chunk_size_threshold "$chunk_size_threshold" \
  "$@"
