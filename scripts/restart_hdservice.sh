#!/usr/bin/env bash
set -euo pipefail

# 进入项目根目录。
cd ~/workspace/arm-hand-teleop

# 先停服务，再重新拉起。
./scripts/stop_hdservice.sh || true
sleep 1
./scripts/start_hdservice.sh "$@"
