# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Teleoperation, data collection, replay, and policy inference stack for AGIBOT O10 arms
(6-DOF) + OmniHand dexterous hands (10-DOF) + RealSense cameras, driven by a Pico VR
headset for arms and Udexreal gloves for hands. Built on the vendored `lerobot_play`
package. Supports single-arm (left or right) and dual-arm configurations.

## Common Commands

Scripts auto-discover Python via [scripts/lib/common_env.sh](scripts/lib/common_env.sh):
`ARM_HAND_TELEOP_PYTHON` env var → `./.venv/bin/python` → `~/miniconda3/envs/arm-hand-teleop/bin/python` → `python3`.
You only need `conda activate arm-hand-teleop` for manual `python`/pip/pytest work.

Main launcher dispatches lerobot_play subcommands and repo scripts:

```bash
python run_lerobot_play.py help                        # list commands
python run_lerobot_play.py {record|replay|infer|control|train} --config_path <yaml>
python run_lerobot_play.py {set_pose|save_reset_pose|save_dual_reset_pose} [args]
```

Shell wrappers in [scripts/](scripts/) preset configs and do pre-flight checks (CAN
interfaces, duplicate processes): `control_o10_{right,left,dual}.sh`,
`record_o10_*.sh`, `replay_o10_*.sh`, `infer_o10_*.sh` (plus `infer_o10_right_cpu.sh`).

Glove service lifecycle: `start_hdservice.sh [--background]`, `stop_hdservice.sh`,
`restart_hdservice.sh`, `start_hdweb.sh` / `stop_hdweb.sh` (HDWeb dashboard).

Tests (disable plugin autoload to avoid ROS leakage):

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_agibot_o10.py       # single file
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_agibot_o10.py::test_name
```

Vendored OmniHand SDK (C++): `cd yudie/vendor_sdk/Omnihand-2025-SDK-dev_xuqigui && ./build.sh -DCMAKE_BUILD_TYPE=Release`;
format with `./format.sh` (requires `clang-format-15`).

## Architecture

Three loosely-coupled layers; respect the boundaries when adding features.

### Layer 1 — `run_lerobot_play.py` launcher

Single entry point. Prepends
`qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any` to `sys.path`,
then imports and runs `lerobot_play.<command>.main()` for `record|replay|infer|control|train`,
or `scripts.<name>.main()` for repo-local helper scripts. All shell launchers funnel
through this file — do not invoke vendored `lerobot_play` modules directly.

### Layer 2 — vendored `lerobot_play` (`qiuzhi/.../lerobot_play/`)

The platform: hydra-style config loading, LeRobot v3.0 dataset IO, policy inference,
per-mode entry modules (`control.py`, `record.py`, `replay.py`, `infer.py`, `train.py`).
Hardware integration lives in:

- `robots/pico_follower_single_arm_agibot_o10/` and `.../pico_follower_dual_arm_agibot_o10/`
  — the "follower" classes that own CAN buses, arm IK, OmniHand CANFD, RealSense cameras,
  and the reset-pose flow. `config_*.py` declares the hydra config schema; `airbot_*.py`
  implements the control loop.
- `teleoperators/pico_leader_single_arm_agibot_o10/` and `.../pico_leader_dual_arm_agibot_o10/`
  — the "leader" side: Pico WebRTC → arm IK targets, VR button mapping, glove or
  `trigger_gesture` hand dispatch, `arm_trigger_mode` handling (`split|left|right|both`).

Treat this tree as a vendor snapshot; root CLAUDE.md guideline §3 (surgical changes)
applies strongly here. Note that `qiuzhi/` and `yudie/` carry their own `.git` metadata
while the root repo tracks gitlinks — be explicit in commits about which layer changed.

### Layer 3 — `yudie/` glove + OmniHand runtime

Independent daemon stack feeding the robots layer:

- [yudie/DexHand_Motion_Control_Program.py](yudie/DexHand_Motion_Control_Program.py)
  — main hand control loop (runnable standalone: `--mode agibotHand_O10 --hand {left,right}`).
- [yudie/Data_Receiver.py](yudie/Data_Receiver.py) — UDP:7777 glove receiver.
- [yudie/sdk_bootstrap.py](yudie/sdk_bootstrap.py) — loads the vendored `omnihand_2025/` SDK.
- [yudie/AGIBOT/](yudie/AGIBOT/) — per-hand adapters; follow the existing `*_yudie.py` naming.
- `vendor_sdk/Omnihand-2025-SDK-dev_xuqigui/` — C++ SDK (build with its own scripts).
- HDService (`start_hdservice.sh`) must be running before `hand_mode: glove` sessions.

### Configuration surface ([configs/](configs/))

Configs are the primary behavior knob — prefer editing YAML over code:

- `left_arm/`, `right_arm/`, `dual_arm/` contain one YAML per mode
  (`o10_*_control|record|replay|infer.yaml`).
- `reset_poses/o10_dual_reset.json` is the canonical reset pose for both arms and
  all pre-set hand gestures. YAML references it via `reset_poses_path`; YAML's
  `reset_gesture` picks a gesture (e.g. `pinch`, `tripod`). Overwrite only via
  `scripts/tools/save_reset_pose.py` or `scripts/tools/save_gesture_reset_poses.py` — runtime
  never rewrites it.
- Switching arm handedness: change `robot.handedness` and `teleop.handedness`; set
  `robot.channel_id: null` to auto-map (left→0, right→1).
- Key teleop knobs: `teleop.hand_mode` (`glove` | `trigger_gesture`),
  `teleop.trigger_gesture` (`pinch` | `tripod`), `teleop.arm_trigger_mode`
  (`split` | `left` | `right` | `both`).

### Data / control flow

Pico VR (WebRTC 8000/8001) → arm IK targets; Udexreal glove (UDP 7777) → hand joint
mapping; hand CANFD over multiChannel (channel 0 = left, 1 = right); arms on CAN0
(left) / CAN1 (right). Recorded tensor shapes: `action` 16D (6 arm + 10 hand),
`observation.state` 23D (6 arm + 10 hand + 7D end-effector pose), plus
`observation.images.{right,top,...}`. Arm+hand states come from the same
`get_observation()` call; cameras and glove use latest-value background threads.

## Coding Conventions (from [AGENTS.md](AGENTS.md))

- Python: 4-space indent, `snake_case`, type hints on new logic. Preserve
  existing camelCase flag names (e.g. `--dataType`, `--canType`) — they are public.
- Shell scripts: descriptive names (`repo_root`, `python_bin`, `config_path`), not
  cryptic single letters.
- C++ SDK: obey `.clang-format`; run `format.sh` (clang-format-15).
- Prefer extracting shared logic (strategy/adapter/factory/template method) over
  copying device-specific branches across `record`, `control`, teleoperator classes.
- Treat `*.zip`, `*.whl`, `.so`, `__pycache__/`, and generated `Protobuf/*_pb2.py` as
  vendor artifacts unless regeneration is in scope.

## Commit Message Format

All git commit messages must follow the `heliangp:提交内容` format
(e.g. `heliangp:fix JSON role fallback`, `heliangp:add cylindrical_straight gesture`).

## Behavioral Guidelines

Bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

Don't assume. Don't hide confusion. Surface tradeoffs.

- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

### 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Mention unrelated dead code — don't delete it.
- Remove imports/variables/functions that *your* changes orphaned; leave pre-existing
  dead code alone unless asked.

### 4. Goal-Driven Execution

Define success criteria. Loop until verified.

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan with per-step verification.
