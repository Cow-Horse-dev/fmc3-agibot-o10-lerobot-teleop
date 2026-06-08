#!/usr/bin/env bash
set -euo pipefail

ARM_HAND_TELEOP_PYTHON="${ARM_HAND_TELEOP_PYTHON:-$HOME/miniconda3/envs/arm-hand-teleop-pi0/bin/python}"

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

openpi_root="${ARM_HAND_TELEOP_OPENPI_ROOT:-$HOME/workspace/openpi}"
openpi_client_pythonpath="$openpi_root/packages/openpi-client/src${PYTHONPATH:+:$PYTHONPATH}"
infer_config="${ARM_HAND_TELEOP_OPENPI_JAX_WS_INFER_CONFIG:-$arm_hand_teleop_repo_root/configs/dual_arm/o10_dual_openpi_jax_ws_infer.yaml}"
server_host="${ARM_HAND_TELEOP_OPENPI_WS_HOST:-localhost}"
server_port="${ARM_HAND_TELEOP_OPENPI_WS_PORT:-8000}"
server_address="${server_host}:${server_port}"
fps="${ARM_HAND_TELEOP_ASYNC_FPS:-30}"
actions_per_chunk="${ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK:-50}"
chunk_size_threshold="${ARM_HAND_TELEOP_ASYNC_CHUNK_SIZE_THRESHOLD:-0.8}"
default_task="${ARM_HAND_TELEOP_OPENPI_DEFAULT_PROMPT:-sort the express parcels}"
num_episodes="${ARM_HAND_TELEOP_NUM_EPISODES:-100000}"
episode_time_sec="${ARM_HAND_TELEOP_EPISODE_TIME_SEC:-3600}"

export ARM_HAND_TELEOP_OPENPI_ROOT="$openpi_root"
export ARM_HAND_TELEOP_OPENPI_CONFIG="${ARM_HAND_TELEOP_OPENPI_CONFIG:-pi05_parcel_sorting}"
export ARM_HAND_TELEOP_OPENPI_DEFAULT_PROMPT="$default_task"
export ARM_HAND_TELEOP_OPENPI_ACTION_DIM="${ARM_HAND_TELEOP_OPENPI_ACTION_DIM:-14}"
export ARM_HAND_TELEOP_RTC_ENABLED="${ARM_HAND_TELEOP_RTC_ENABLED:-1}"
export ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON="${ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON:-10}"
export ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT="${ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT:-10.0}"
export ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE="${ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE:-EXP}"
export ARM_HAND_TELEOP_ASYNC_FPS="$fps"
export ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK="$actions_per_chunk"
export PYTHONPATH="$openpi_client_pythonpath"

if [[ ! -d "$openpi_root/packages/openpi-client/src/openpi_client" ]]; then
  echo "OpenPI client source not found: $openpi_root/packages/openpi-client/src/openpi_client" >&2
  exit 1
fi

"$arm_hand_teleop_python_bin" - <<'PY'
import importlib

for module_name in ("msgpack", "websockets", "openpi_client.websocket_client_policy"):
    importlib.import_module(module_name)
PY

server_pid=""
cleanup() {
  if [[ -n "${server_pid}" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

"$arm_hand_teleop_repo_root/scripts/o10/dual_arm/serve_openpi_jax_policy.sh" &
server_pid="$!"
sleep 8

"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" infer \
  --yaml "$infer_config" \
  --policy openpi_jax_ws \
  --model_path openpi-websocket \
  --task_description "$default_task" \
  --fps "$fps" \
  --num_episodes "$num_episodes" \
  --episode_time_sec "$episode_time_sec" \
  --actions_per_chunk "$actions_per_chunk" \
  --chunk_size_threshold "$chunk_size_threshold" \
  --async_infer \
  --server_address "$server_address" \
  "$@"
