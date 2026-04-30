#!/usr/bin/env bash

arm_hand_teleop_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

arm_hand_teleop_source_ros() {
  if [ -n "${ROS_DISTRO:-}" ] && [ -n "${AMENT_PREFIX_PATH:-}" ]; then
    return 0
  fi

  local ros_setup=""
  local restore_nounset=0
  for ros_setup in \
    "/opt/ros/jazzy/setup.bash" \
    "/opt/ros/humble/setup.bash"
  do
    if [ -f "${ros_setup}" ]; then
      if [[ $- == *u* ]]; then
        restore_nounset=1
        set +u
      fi
      # shellcheck disable=SC1090
      source "${ros_setup}"
      if [ "${restore_nounset}" -eq 1 ]; then
        set -u
      fi
      return 0
    fi
  done

  return 0
}

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
    ~/miniconda3/envs/arm-hand-teleop/bin/python \
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
arm_hand_teleop_source_ros
