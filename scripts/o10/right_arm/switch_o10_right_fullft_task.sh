#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/common_env.sh"

cd "$arm_hand_teleop_repo_root"

task_config="${ARM_HAND_TELEOP_PI05_FULLFT_TASK_CONFIG:-$arm_hand_teleop_repo_root/configs/right_arm/o10_right_pi05_fullft_merged_tasks.yaml}"
profile_id="${1:-}"

if [[ -z "$profile_id" ]]; then
  echo "Usage: $0 <black_to_yellow|yellow_to_black>" >&2
  exit 2
fi

"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" switch_lora_task \
  --config "$task_config" \
  --profile "$profile_id"
