#!/usr/bin/env bash
set -euo pipefail

ARM_HAND_TELEOP_PYTHON="${ARM_HAND_TELEOP_PYTHON:-$HOME/miniconda3/envs/arm-hand-teleop/bin/python}"

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

if [[ $# -gt 0 && "$1" != --* ]]; then
  checkpoint="$1"
  shift
else
  checkpoint="${ARM_HAND_TELEOP_SMOLVLA_CHECKPOINT:-100000}"
fi
model_base="${SMOLVLA_MODEL_BASE:-$HOME/workspace/mymodels/qiuzhi_agibot/camera_pen_touch_clean_del_52_376/smolvla/smolvla_cam_pen_wandb_20260502_011554}"
if [[ "$checkpoint" = /* ]]; then
  model_path="$checkpoint"
else
  model_path="${model_base}/checkpoints/${checkpoint}/pretrained_model"
fi

server_host="${ARM_HAND_TELEOP_ASYNC_SERVER_HOST:-localhost}"
server_port="${ARM_HAND_TELEOP_ASYNC_SERVER_PORT:-8080}"
server_address="${server_host}:${server_port}"
fps="${ARM_HAND_TELEOP_ASYNC_FPS:-30}"
inference_latency="${ARM_HAND_TELEOP_ASYNC_INFERENCE_LATENCY:-0.30}"
actions_per_chunk="${ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK:-50}"
chunk_size_threshold="${ARM_HAND_TELEOP_ASYNC_CHUNK_SIZE_THRESHOLD:-0.6}"

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
  --policy smolvla \
  --model_path "$model_path" \
  --async_infer \
  --fps "$fps" \
  --server_address "$server_address" \
  --actions_per_chunk "$actions_per_chunk" \
  --chunk_size_threshold "$chunk_size_threshold" \
  "$@"
