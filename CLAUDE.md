# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Robotic arm + dexterous hand teleoperation and data collection system for the AGIBOT O10 single-arm robot with OmniHand dexterous hands. Enables real-time teleoperation via Pico VR headset + Udexreal glove, data recording in LeRobot v3.0 format, trajectory replay, and policy inference.

## Commands

```bash
# Main entry points (scripts auto-detect Python via ARM_HAND_TELEOP_PYTHON, .venv, conda, or python3)
./scripts/control_o10_right.sh          # Real-time teleoperation
./scripts/record_o10_right.sh           # Data recording
./scripts/replay_o10_right.sh           # Trajectory replay
./scripts/infer_o10_right.sh            # Policy inference

# Hand glove service
./scripts/start_hdservice.sh [--background]
./scripts/stop_hdservice.sh
./scripts/restart_hdservice.sh
./scripts/start_hdweb.sh                # Web dashboard

# Direct Python launcher
python run_lerobot_play.py help
python run_lerobot_play.py record --yaml configs/o10_right_record.yaml
python run_lerobot_play.py control --yaml configs/o10_right_control.yaml

# Hand motion control (direct)
python yudie/DexHand_Motion_Control_Program.py --mode agibotHand_O10 --hand right --dataType Json --ip 127.0.0.1 --port 7777 --canType multiChannel

# Tests (disable ROS plugin autoload to avoid leakage)
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_agibot_o10.py
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/

# Vendor SDK rebuild
cd yudie/vendor_sdk/Omnihand-2025-SDK-dev_xuqigui && ./build.sh -DCMAKE_BUILD_TYPE=Release
cd yudie/vendor_sdk/Omnihand-2025-SDK-dev_xuqigui && ./format.sh   # requires clang-format-15
```

## Architecture

Two largely independent subsystems:

**LeRobot subsystem** (`qiuzhi/`): Vendored `lerobot_play` snapshot handles arm teleoperation, dataset recording, replay, and inference. `run_lerobot_play.py` bootstraps the package tree. Configs in `configs/*.yaml` drive all modes.

**Hand/glove subsystem** (`yudie/`): `DexHand_Motion_Control_Program.py` is the main loop — reads glove UDP data via `Data_Receiver.py`, maps finger angles to hand joints, and sends commands via OmniHand SDK. Hand adapters live in `yudie/AGIBOT/*_yudie.py` (O10/O12 variants). Vendor SDK binaries in `yudie/omnihand_2025/` and `yudie/vendor_sdk/`.

**Data flow**:
1. Pico VR (WebRTC, ports 8000/8001) → arm IK via Teleoperator
2. Udexreal glove (UDP, port 7777, JSON/Protobuf) → hand joint mapping
3. Commands → O10 arm (CAN, can0) + OmniHand (multiChannel CAN)
4. Observations (6 arm + 10 hand joints + 7D EEF pose + RealSense frames) → LeRobot v3.0 dataset

**Dataset**: Action is 16D (6 arm + 10 hand), observation.state is 23D (6+10+7). Default root: `~/workspace/dataset/Robot/agi_arm_bot/`.

## Coding Conventions

- Python: 4-space indent, `snake_case` for functions/modules, type hints on new logic
- Preserve existing public flag names even if camelCase (`--dataType`, `--canType`)
- New hand adapters go in `yudie/AGIBOT/` as `*_yudie.py`
- Shell scripts: descriptive variable names (`repo_root`, `config_path`, `python_bin`)
- C++ vendor SDK: follow `.clang-format`, use `format.sh` with clang-format-15
- Treat `*.zip`, `*.whl`, `.so` files, `__pycache__/`, and `Protobuf/*_pb2.py` as vendor artifacts

## Testing

Tests live in `qiuzhi/tests/test_*.py`. Prefer pure-Python regression tests that stub SDK imports — no CAN hardware required. No coverage gate; each behavior change should ship with a focused test or a manual validation note.

## Repo Structure Notes

`qiuzhi/` and `yudie/` each contain their own Git metadata while the root repo tracks gitlinks. Be explicit about whether changes are in nested repos, root pointers, or both. Commits should be short and scoped (e.g., `yudie: fix JSON role fallback`).
