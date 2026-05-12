#!/usr/bin/env bash
set -euo pipefail

ARM_HAND_TELEOP_PYTHON="${ARM_HAND_TELEOP_PYTHON:-$HOME/miniconda3/envs/arm-hand-teleop/bin/python}"

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

multi_lora_config="${ARM_HAND_TELEOP_PI05_MULTI_LORA_CONFIG:-$arm_hand_teleop_repo_root/configs/right_arm/o10_right_pi05_lora_tasks.yaml}"
server_host="${ARM_HAND_TELEOP_ASYNC_SERVER_HOST:-localhost}"
server_port="${ARM_HAND_TELEOP_ASYNC_SERVER_PORT:-8080}"
server_address="${server_host}:${server_port}"
fps="${ARM_HAND_TELEOP_ASYNC_FPS:-15}"
inference_latency="${ARM_HAND_TELEOP_ASYNC_INFERENCE_LATENCY:-0.35}"
actions_per_chunk="${ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK:-50}"
chunk_size_threshold="${ARM_HAND_TELEOP_ASYNC_CHUNK_SIZE_THRESHOLD:-0.8}"
use_async="${ARM_HAND_TELEOP_MULTI_LORA_ASYNC:-1}"
default_task="${ARM_HAND_TELEOP_MULTI_LORA_DEFAULT_TASK:-use the right arm to move the tissue from the black paper to the yellow paper}"

export ARM_HAND_TELEOP_RTC_ENABLED="${ARM_HAND_TELEOP_RTC_ENABLED:-1}"
export ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON="${ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON:-10}"
export ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT="${ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT:-10.0}"
export ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE="${ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE:-EXP}"

server_pid=""
cleanup() {
  if [[ -n "${server_pid}" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

infer_args=(
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" infer
  --yaml "$arm_hand_teleop_repo_root/configs/right_arm/o10_right_infer.yaml"
  --policy pi05
  --model_path "$multi_lora_config"
  --task_description "$default_task"
  --fps "$fps"
  --actions_per_chunk "$actions_per_chunk"
  --chunk_size_threshold "$chunk_size_threshold"
)

if [[ "$use_async" == "1" || "$use_async" == "true" ]]; then
  "$arm_hand_teleop_python_bin" \
    "$arm_hand_teleop_repo_root/run_lerobot_play.py" async_policy_server \
    --host "$server_host" \
    --port "$server_port" \
    --fps "$fps" \
    --inference_latency "$inference_latency" &
  server_pid="$!"
  sleep 2

  infer_args+=(--async_infer --server_address "$server_address")
fi

"$arm_hand_teleop_python_bin" "${infer_args[@]}" "$@"
