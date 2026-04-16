#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common_env.sh"

image_name="${ARM_HAND_TELEOP_IMAGE:-arm-hand-teleop:jazzy}"

cd "$arm_hand_teleop_repo_root"

docker build \
  --file "$arm_hand_teleop_repo_root/docker/Dockerfile" \
  --tag "$image_name" \
  "$arm_hand_teleop_repo_root"
