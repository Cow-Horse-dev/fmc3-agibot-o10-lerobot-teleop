#!/usr/bin/env bash
set -euo pipefail

ARM_HAND_TELEOP_PYTHON="${ARM_HAND_TELEOP_PYTHON:-$HOME/miniconda3/envs/arm-hand-teleop-pi0/bin/python}"

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

openpi_root="${ARM_HAND_TELEOP_OPENPI_ROOT:-$HOME/workspace/openpi}"
openpi_pythonpath="$openpi_root/src:$openpi_root/packages/openpi-client/src${PYTHONPATH:+:$PYTHONPATH}"
openpi_jax_python="${ARM_HAND_TELEOP_OPENPI_JAX_PYTHON:-$HOME/miniconda3/envs/openpi-jax/bin/python}"
openpi_checkpoint="${ARM_HAND_TELEOP_OPENPI_CHECKPOINT:-$HOME/workspace/mymodels/agi_arm_bot/jax/pi05/parcel_sorting_v21_full/130000}"
infer_config="${ARM_HAND_TELEOP_OPENPI_JAX_INFER_CONFIG:-$arm_hand_teleop_repo_root/configs/dual_arm/o10_dual_openpi_jax_infer.yaml}"
server_host="${ARM_HAND_TELEOP_ASYNC_SERVER_HOST:-localhost}"
server_port="${ARM_HAND_TELEOP_ASYNC_SERVER_PORT:-8080}"
server_address="${server_host}:${server_port}"
fps="${ARM_HAND_TELEOP_ASYNC_FPS:-30}"
inference_latency="${ARM_HAND_TELEOP_ASYNC_INFERENCE_LATENCY:-0.35}"
actions_per_chunk="${ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK:-50}"
chunk_size_threshold="${ARM_HAND_TELEOP_ASYNC_CHUNK_SIZE_THRESHOLD:-0.8}"
default_task="${ARM_HAND_TELEOP_OPENPI_DEFAULT_PROMPT:-sort the express parcels}"

export ARM_HAND_TELEOP_OPENPI_CONFIG="${ARM_HAND_TELEOP_OPENPI_CONFIG:-pi05_parcel_sorting}"
export ARM_HAND_TELEOP_OPENPI_DEFAULT_PROMPT="$default_task"
export ARM_HAND_TELEOP_OPENPI_ACTION_DIM="${ARM_HAND_TELEOP_OPENPI_ACTION_DIM:-14}"
export ARM_HAND_TELEOP_RTC_ENABLED="${ARM_HAND_TELEOP_RTC_ENABLED:-1}"
export ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON="${ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON:-10}"
export ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT="${ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT:-10.0}"
export ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE="${ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE:-EXP}"
export OPENPI_DATA_HOME="${OPENPI_DATA_HOME:-$openpi_root/openpi_cache}"
export HF_LEROBOT_HOME="${HF_LEROBOT_HOME:-$openpi_root/datasets}"
export HF_DATASETS_CACHE="${HF_DATASETS_CACHE:-$openpi_root/openpi_cache/hf_datasets}"
export XLA_PYTHON_CLIENT_MEM_FRACTION="${XLA_PYTHON_CLIENT_MEM_FRACTION:-0.85}"

if [[ ! -x "$openpi_jax_python" ]]; then
  echo "OpenPI JAX Python not found or not executable: $openpi_jax_python" >&2
  exit 1
fi

if [[ ! -d "$openpi_checkpoint/params" ]]; then
  echo "OpenPI checkpoint must contain params/: $openpi_checkpoint" >&2
  exit 1
fi

if [[ ! -d "$openpi_checkpoint/assets" ]]; then
  echo "OpenPI checkpoint must contain assets/: $openpi_checkpoint" >&2
  exit 1
fi

PYTHONPATH="$openpi_pythonpath" "$openpi_jax_python" - <<'PY'
import os

from openpi.training import config as openpi_config

config_name = os.environ["ARM_HAND_TELEOP_OPENPI_CONFIG"]
openpi_config.get_config(config_name)
PY

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
  --yaml "$infer_config"
  --policy openpi_jax
  --model_path "$openpi_checkpoint"
  --task_description "$default_task"
  --fps "$fps"
  --actions_per_chunk "$actions_per_chunk"
  --chunk_size_threshold "$chunk_size_threshold"
  --async_infer
  --server_address "$server_address"
)

"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" async_policy_server \
  --host "$server_host" \
  --port "$server_port" \
  --fps "$fps" \
  --inference_latency "$inference_latency" &
server_pid="$!"
sleep 2

"$arm_hand_teleop_python_bin" "${infer_args[@]}" "$@"
