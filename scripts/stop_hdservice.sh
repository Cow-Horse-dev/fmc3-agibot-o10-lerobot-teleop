#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common_env.sh"

# 停掉 HDService。
exec "$arm_hand_teleop_repo_root/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64/stop_hdservice.sh" "$@"
