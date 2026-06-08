#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

openpi_root="${ARM_HAND_TELEOP_OPENPI_ROOT:-$HOME/workspace/openpi}"
openpi_jax_python="${ARM_HAND_TELEOP_OPENPI_JAX_PYTHON:-$HOME/miniconda3/envs/openpi-jax/bin/python}"
openpi_checkpoint="${ARM_HAND_TELEOP_OPENPI_CHECKPOINT:-$HOME/workspace/mymodels/agi_arm_bot/jax/pi05/parcel_sorting_v21_full/130000}"
openpi_config="${ARM_HAND_TELEOP_OPENPI_CONFIG:-pi05_parcel_sorting}"
default_prompt="${ARM_HAND_TELEOP_OPENPI_DEFAULT_PROMPT:-sort the express parcels}"
server_port="${ARM_HAND_TELEOP_OPENPI_WS_PORT:-8000}"
fps="${ARM_HAND_TELEOP_ASYNC_FPS:-30}"
inference_latency="${ARM_HAND_TELEOP_ASYNC_INFERENCE_LATENCY:-0.35}"
actions_per_chunk="${ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK:-50}"
rtc_enabled="${ARM_HAND_TELEOP_RTC_ENABLED:-1}"
rtc_flag="--rtc-enabled"
case "${rtc_enabled,,}" in
  0|false|no|off)
    rtc_flag="--no-rtc-enabled"
    ;;
esac

export OPENPI_DATA_HOME="${OPENPI_DATA_HOME:-$openpi_root/openpi_cache}"
export HF_LEROBOT_HOME="${HF_LEROBOT_HOME:-$openpi_root/datasets}"
export HF_DATASETS_CACHE="${HF_DATASETS_CACHE:-$openpi_root/openpi_cache/hf_datasets}"
export XLA_PYTHON_CLIENT_MEM_FRACTION="${XLA_PYTHON_CLIENT_MEM_FRACTION:-0.85}"

if [[ ! -x "$openpi_jax_python" ]]; then
  echo "OpenPI JAX Python not found or not executable: $openpi_jax_python" >&2
  exit 1
fi

if [[ ! -d "$openpi_root/src/openpi" ]]; then
  echo "OpenPI repo not found: $openpi_root" >&2
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

cd "$openpi_root"

"$openpi_jax_python" scripts/serve_policy.py \
  --default-prompt="$default_prompt" \
  --port="$server_port" \
  "$rtc_flag" \
  --rtc-actions-per-chunk="$actions_per_chunk" \
  --rtc-fps="$fps" \
  --rtc-inference-latency="$inference_latency" \
  --rtc-execution-horizon="${ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON:-10}" \
  --rtc-max-guidance-weight="${ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT:-10.0}" \
  --rtc-prefix-attention-schedule="${ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE:-EXP}" \
  policy:checkpoint \
  --policy.config="$openpi_config" \
  --policy.dir="$openpi_checkpoint"
