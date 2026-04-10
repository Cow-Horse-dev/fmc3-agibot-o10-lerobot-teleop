#!/usr/bin/env bash
set -euo pipefail

# O10 右臂录制脚本。
# 默认读取 `configs/o10_right_record.yaml`，也可以用 CONFIG_PATH 覆盖。

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
python_bin="${PYTHON_BIN:-$HOME/miniconda3/envs/arm-hand-teleop/bin/python}"
config_path="${CONFIG_PATH:-$repo_root/configs/o10_right_record.yaml}"

"$python_bin" \
  "$repo_root/run_lerobot_play.py" record \
  --yaml "$config_path" \
  "$@"
