#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common_env.sh"

image_name="${ARM_HAND_TELEOP_IMAGE:-arm-hand-teleop:jazzy}"
timestamp="$(date +%Y%m%d_%H%M%S)"
output_path="${1:-$arm_hand_teleop_repo_root/dist/arm-hand-teleop_${timestamp}.tar.gz}"

mkdir -p "$(dirname "$output_path")"
docker image inspect "$image_name" >/dev/null
docker save "$image_name" | gzip > "$output_path"

echo "Exported image to $output_path"
