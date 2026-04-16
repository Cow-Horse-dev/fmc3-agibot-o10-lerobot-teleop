#!/usr/bin/env bash

arm_hand_teleop_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

arm_hand_teleop_find_python_bin() {
  local candidate_python=""

  if [ -n "${ARM_HAND_TELEOP_PYTHON:-}" ]; then
    candidate_python="${ARM_HAND_TELEOP_PYTHON}"
    if [ -x "${candidate_python}" ]; then
      printf '%s\n' "${candidate_python}"
      return 0
    fi
  fi

  for candidate_python in \
    "${arm_hand_teleop_repo_root}/.venv/bin/python" \
    "/home/phl/miniconda3/envs/arm-hand-teleop/bin/python" \
    "/opt/conda/envs/arm-hand-teleop/bin/python" \
    "$(command -v python3 2>/dev/null || true)" \
    "$(command -v python 2>/dev/null || true)"
  do
    if [ -n "${candidate_python}" ] && [ -x "${candidate_python}" ]; then
      printf '%s\n' "${candidate_python}"
      return 0
    fi
  done

  echo "Unable to find a usable Python interpreter. Set ARM_HAND_TELEOP_PYTHON." >&2
  return 1
}

arm_hand_teleop_python_bin="$(arm_hand_teleop_find_python_bin)"
