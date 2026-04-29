# arm-hand-teleop

Teleoperation, data collection, replay, and policy inference system for Agibot O10 single-arm/dual-arm setups with OmniHand dexterous hands and RealSense/USB cameras.

The project is built on a vendored `lerobot_play` snapshot. The main input devices are Pico VR controllers/wrist poses. Hand input can come from Udexreal gloves (`glove`) or VR grip-triggered gestures (`trigger_gesture`).

## Directory Overview

- `configs/`: control, record, infer, replay configs, plus reset-pose JSON files.
- `scripts/`: daily launch scripts, HDService/HDWeb service scripts, and utility scripts.
- `qiuzhi/`: vendored `lerobot_play` code and Python regression tests.
- `yudie/`: Udexreal glove, OmniHand, HDService, HDWeb code and SDKs.
- `run_lerobot_play.py`: unified project entry point; all O10 scripts wrap it.

## Environment And Python Interpreter

For daily shell scripts, you usually do not need to run `conda activate` manually. Scripts under `scripts/o10/` and `scripts/services/` find Python in this order:

```text
ARM_HAND_TELEOP_PYTHON > .venv/bin/python > ~/miniconda3/envs/arm-hand-teleop/bin/python > python3
```

Enter the environment only when running Python, installing packages, or running tests manually:

```bash
conda activate arm-hand-teleop
```

You can also explicitly set the interpreter:

```bash
ARM_HAND_TELEOP_PYTHON=/your/python ./scripts/o10/right_arm/control_o10_right.sh
```

Tests require `pytest`; install it if missing:

```bash
conda activate arm-hand-teleop
pip install pytest
```

## Unified Entry Point

Daily use should prefer `scripts/o10/.../*.sh`. When calling the Python entry point directly, note the different argument names:

```bash
python run_lerobot_play.py help

# control uses --config_path
python run_lerobot_play.py control --config_path configs/right_arm/o10_right_control.yaml

# record / replay / infer use --yaml
python run_lerobot_play.py record --yaml configs/right_arm/o10_right_record.yaml
python run_lerobot_play.py replay --yaml configs/right_arm/o10_right_replay.yaml
python run_lerobot_play.py infer  --yaml configs/right_arm/o10_right_infer.yaml

# other tool entries
python run_lerobot_play.py set_pose [args]
python run_lerobot_play.py save_reset_pose [args]
python run_lerobot_play.py save_dual_reset_pose [args]
```

## Common Launch Commands

Go to the repo root first:

```bash
cd ~/workspace/arm-hand-teleop
```

### Glove Service

`hand_mode: glove` requires HDService first; `trigger_gesture` does not need the glove service.

```bash
./scripts/services/start_hdservice.sh              # foreground
./scripts/services/start_hdservice.sh --background # background
./scripts/services/stop_hdservice.sh
./scripts/services/restart_hdservice.sh

./scripts/services/start_hdweb.sh                  # HDWeb dashboard
./scripts/services/stop_hdweb.sh
```

### Single Right Arm

```bash
./scripts/o10/right_arm/control_o10_right.sh       # live teleoperation
./scripts/o10/right_arm/record_o10_right.sh        # data recording
./scripts/o10/right_arm/replay_o10_right.sh        # trajectory replay
./scripts/o10/right_arm/infer_o10_right.sh         # GPU policy inference
./scripts/o10/right_arm/infer_o10_right_cpu.sh     # CPU inference example
```

### Single Left Arm

```bash
./scripts/o10/left_arm/control_o10_left.sh         # live teleoperation
./scripts/o10/left_arm/record_o10_left.sh          # data recording
./scripts/o10/left_arm/replay_o10_left.sh          # trajectory replay
./scripts/o10/left_arm/infer_o10_left.sh           # policy inference
```

### Dual Arm

```bash
./scripts/o10/dual_arm/control_o10_dual.sh         # live teleoperation
./scripts/o10/dual_arm/record_o10_dual.sh          # data recording
./scripts/o10/dual_arm/replay_o10_dual.sh          # trajectory replay
./scripts/o10/dual_arm/infer_o10_dual.sh           # policy inference
```

## Pico Control Logic

The current configs and code are aligned as follows.

| Mode | Motion Input | Enable | Stop + Reset | Hold-To-Control Gate |
|---|---|---|---|---|
| Left single arm | Left controller controls left arm/hand | Right controller `A` | Right controller `B` | Right controller `RTr` |
| Right single arm | Right controller controls right arm/hand | Left controller `X` | Left controller `Y` | Left controller `LTr` |
| Dual arm | Left controller controls left arm/hand, right controller controls right arm/hand | Left controller `X` | Left controller `Y` | Left controller `LTr` |

Notes:

- Press the enable button first to enter teleop. Arm IK and hand control only output following commands while the gate trigger is held.
- In single-arm mode, the working controller only provides motion input for that arm/hand; the opposite controller handles enable, reset, and gate.
- In dual-arm configs, `teleop.arm_trigger_mode: left`, so both arms/hands use the left controller `X/Y/LTr` gate.
- Other dual-arm `arm_trigger_mode` values:
  - `left`: hold `LTr` for both arms to follow (current default).
  - `right`: hold `RTr` for both arms to follow.
  - `both`: hold `LTr + RTr` together for both arms to follow.
  - `split`: left arm uses `LTr`, right arm uses `RTr`.

## Hand Control Modes

Hand control has two layers: `hand_mode` chooses where hand input comes from; `hand_action_mode` chooses which dimensionality is written to action and sent to the robot.

### Hand Input Source: `teleop.hand_mode`

- `glove`: use HDService + Udexreal gloves for real-time finger-joint following. Start HDService first and confirm the correct left/right hands are online in HDWeb.
- `trigger_gesture`: do not use gloves. VR controller grip controls preset hand gesture opening/closing. The default is `open`; pressing the working-side grip or crossing the grip-axis threshold switches to `closed`.

`trigger_gesture` details:

- Left single arm: the left controller drives left arm/hand motion, so gesture grasp uses left controller `LG` / `leftGrip`.
- Right single arm: the right controller drives right arm/hand motion, so gesture grasp uses right controller `RG` / `rightGrip`.
- Dual arm: left hand uses `LG` / `leftGrip`; right hand uses `RG` / `rightGrip`.
- Single-arm grip threshold is hard-coded to `0.2`; dual-arm threshold can be overridden with `teleop.grasp_grip_threshold`, default `0.2`.
- `teleop.trigger_gesture` selects the closed-pose shape, commonly `pinch` or `tripod`.
- Dual-arm configs can set different gestures per side with `teleop.left.trigger_gesture` / `teleop.right.trigger_gesture`.

### Hand Action Dimensionality: `hand_action_mode`

- `dexterous_10d`: 10D dexterous-hand joint control. Action/state keep the 10 O10 hand joints, suitable for full finger teleoperation and recording.
- `gripper_1d`: 1D gripper control. Action only keeps `gripper.pos`; runtime maps it back to O10 10D hand joints using `gripper_gesture` and the reset pose `open` / `closed` states.

`hand_mode` and `hand_action_mode` can be combined:

| Input Source | Action Dimensionality | Effect |
|---|---|---|
| `glove` | `dexterous_10d` | Gloves directly control 10D finger joints and record full 10D hand motion |
| `glove` | `gripper_1d` | Gloves first map to 10D, then project to 1D `gripper.pos` for recording/control |
| `trigger_gesture` | `dexterous_10d` | Controller grip switches between preset `open/closed` 10D gestures |
| `trigger_gesture` | `gripper_1d` | Controller grip directly controls 1D `gripper.pos`, then restores a preset gesture |

During `control` and `record`, `teleop.hand_action_mode` defaults to `robot.hand_action_mode`; if both are written, keep them consistent. `replay` / `infer` have no teleop hand input and interpret the dataset or policy output only through `robot.hand_action_mode`.

## Config Files

### Left Arm

- `configs/left_arm/o10_left_control.yaml`: live control. `controller_side: right`, `wrist_pose_source: left`, cameras `top + left_wrist`.
- `configs/left_arm/o10_left_record.yaml`: data recording. `controller_side: right`, `wrist_pose_source: left`, cameras `top + left`.
- `configs/left_arm/o10_left_replay.yaml`: trajectory replay.
- `configs/left_arm/o10_left_infer.yaml`: policy inference. Camera keys match the left-arm recording schema: `top + left`.

### Right Arm

- `configs/right_arm/o10_right_control.yaml`: live control. `controller_side: left`, `wrist_pose_source: right`, cameras `top + right_wrist`.
- `configs/right_arm/o10_right_record.yaml`: data recording. `controller_side: left`, `wrist_pose_source: right`, cameras `top + right`.
- `configs/right_arm/o10_right_replay.yaml`: trajectory replay.
- `configs/right_arm/o10_right_infer.yaml`: GPU policy inference. Camera keys match the right-arm recording schema: `top + right`.
- `configs/right_arm/o10_right_infer_cpu.yaml`: CPU inference example, default `policy: act`.

### Dual Arm

- `configs/dual_arm/o10_dual_control.yaml`: live control. `arm_trigger_mode: left`, left/right wrist poses come from `left` / `right`.
- `configs/dual_arm/o10_dual_record.yaml`: data recording. Defaults: `include_eef_pose: false`, `tactile_mode: "none"`.
- `configs/dual_arm/o10_dual_replay.yaml`: trajectory replay.
- `configs/dual_arm/o10_dual_infer.yaml`: policy inference. Must match the dual-arm recording schema: `include_eef_pose: false`, `tactile_mode: "none"`, cameras `top + left_wrist + right_wrist`.

### Reset Poses

- `configs/reset_poses/o10_dual_reset.json`: canonical reset-pose file shared by all O10 control, record, replay, and infer configs:
  - `arm.left` / `arm.right`: target angles for the 6 joints of each arm.
  - `hand.feature_names`: hand joint order (10D).
  - `gestures.<name>.<side>.open|closed`: 10D `open` / `closed` joint values for each gesture (defaults include `pinch` and `tripod`) and side. YAML `reset_gesture` selects `<name>`.
- Runtime only reads this file and never overwrites it automatically. To update it, edit this JSON manually. The `save_*` tools in "Tool Scripts" emit helper JSON files but do not write back to this canonical file.

## Data Flow And Hardware Channels

- Pico WebRTC process publishes:
  - pose: `tcp://localhost:8000`
  - buttons/triggers: `tcp://localhost:8001`
- In the Pico headset VRControl / VR control page, enter the host IPv4 address. Keep the ports as configured: `8000/8001`.
  - Host WiFi IP: `192.168.1.111` (interface `wlo1`)
  - Host wired IP: `192.168.1.138` (interface `enp4s0`)
  - If Pico and the host are on the same WiFi, prefer the WiFi IP. If Pico's network can reach the host's wired subnet, use the wired IP.
  - Do not use `127.0.0.1`, Docker, Tailscale, or `198.18.*` virtual-interface addresses.
  - If the IP changes, recheck with `ip -br addr show wlo1 enp4s0`.
- Udexreal gloves: the HDService script sets `HD_UDP_TARGET=127.0.0.1:5555`; O10 teleop receives on local port `5555`. Used only with `hand_mode: glove`.
- Arm CAN: left arm defaults to `can0`, right arm defaults to `can1`; each YAML's `robot.port` or `robot.left/right.port` is authoritative.
- Hand CANFD: `channel_mode: multiChannel`; when `channel_id: null`, handedness chooses automatically: `left -> 0`, `right -> 1`.

## Camera Config

- Single-arm control uses the same wrist-camera naming as dual-arm configs:
  - left arm: `top + left_wrist`
  - right arm: `top + right_wrist`
- Single-arm record/infer uses dataset schema names:
  - left arm: `top + left`
  - right arm: `top + right`
- Dual-arm control/record/infer uses `top + left_wrist + right_wrist`.
- The top USB camera defaults to `fourcc: MJPG` to avoid unstable OpenCV auto-negotiated formats.
- `robot.allow_camera_read_failures: true` is useful for control/infer: if camera startup fails, the program skips that camera; if reads fail, it uses cached frames or all-zero frames. Recording should usually keep this `false` to avoid corrupt data.

## Data Recording

Recording format is LeRobot `v3.0`. Default dataset root:

```text
~/workspace/dataset/Robot/agi_arm_bot
```

Common recording commands:

```bash
./scripts/o10/right_arm/record_o10_right.sh
./scripts/o10/left_arm/record_o10_left.sh
./scripts/o10/dual_arm/record_o10_dual.sh
```

Override dataset root/name:

```bash
./scripts/o10/right_arm/record_o10_right.sh \
  --dataset.root ~/workspace/dataset/Robot/agi_arm_bot \
  --dataset.repo_id my_dataset
```

With the default `dexterous_10d`, `action` contains arm joints + 10D hand joints:

| Mode | Action Dim | Contents |
|---|---:|---|
| Single arm | 16D | arm 6 + hand 10 |
| Dual arm | 32D | `left.*` 16D + `right.*` 16D |

With `gripper_1d`, the hand action is compressed to 1D:

| Mode | Action Dim | Contents |
|---|---:|---|
| Single arm | 7D | arm 6 + `gripper.pos` |
| Dual arm | 14D | left arm 6 + `left.gripper.pos`, right arm 6 + `right.gripper.pos` |

### O10 `gripper_1d` Mapping

O10 can use `hand_action_mode: gripper_1d` for more compact action recording. Single-arm data is 7D: 6 arm joints + `gripper.pos`; dual-arm data is 14D: left 6 arm joints + `left.gripper.pos`, right 6 arm joints + `right.gripper.pos`.

The recording side still first obtains each O10 hand's 10D finger joints. Then, using `gripper_gesture`, `handedness`, and the reset pose's `open` / `closed` states, it projects the current 10D finger joints to `gripper.pos` in `0..1`. The replay side reads `left.gripper.pos` / `right.gripper.pos` from the dataset and, using the same `gripper_gesture` and `handedness`, linearly interpolates between the matching `open` / `closed` poses to restore 10D finger joints for the O10 hand.

Current dual-arm configs in `configs/dual_arm/o10_dual_record.yaml` and `configs/dual_arm/o10_dual_replay.yaml` use `tripod` for the left hand and `pinch` for the right hand. Replay of the 20260427 dataset is generally aligned, which indicates the record/replay mapping path is working.

`observation.state` is controlled by `robot.include_eef_pose` and `robot.tactile_mode`:

| include_eef_pose | tactile_mode | Single-Arm State | Dual-Arm State |
|---|---|---:|---:|
| `false` | `none` | 16D (current single-arm record default) | 32D |
| `true` | `none` | 23D | 46D |
| `false` | `7d` | 23D | 46D (current dual-arm record default) |
| `true` | `7d` | 30D | 60D |
| `false` | `80d` | 96D | 192D |
| `false` | `130d` | 146D | 292D |

## Inference

Supported policies:

- `act`
- `diffusion`
- `pi0`
- `pi05`
- `smolvla`
- `groot`

Common commands:

```bash
./scripts/o10/left_arm/infer_o10_left.sh
./scripts/o10/right_arm/infer_o10_right.sh
./scripts/o10/right_arm/infer_o10_right_cpu.sh
./scripts/o10/dual_arm/infer_o10_dual.sh
```

Pre-inference checklist:

- `infer.model_path` must exist and contain `config.json`; weights are usually `model.safetensors` or `pytorch_model.bin`.
- `infer.policy` must match the model type.
- `infer.device` can be `cuda` or `cpu`; CPU is only suitable for small models or debugging.
- `robot.include_eef_pose`, `robot.tactile_mode`, and camera keys must match the training dataset, otherwise the policy input schema will not match.
- When `infer.save_data: true`, inference is saved as a LeRobot dataset. If `save_path` is empty, data is written under `~/.cache/huggingface/lerobot/...`.

## Replay

Replay uses `dataset.root` from each replay YAML to point at an existing dataset:

```bash
./scripts/o10/left_arm/replay_o10_left.sh
./scripts/o10/right_arm/replay_o10_right.sh
./scripts/o10/dual_arm/replay_o10_dual.sh
```

To change the replay dataset, edit `dataset.root` / `dataset.repo_id` in the corresponding YAML.

## Tool Scripts

These scripts can be run directly, or through the entry point for the first three:

```bash
python run_lerobot_play.py set_pose [args]              # = scripts/tools/set_pose.py
python run_lerobot_play.py save_reset_pose [args]       # = scripts/tools/save_reset_pose.py
python run_lerobot_play.py save_dual_reset_pose [args]  # = scripts/tools/save_dual_reset_pose.py
```

Common operations:

```bash
# Read current single-arm arm+hand joints and export legacy JSON
# for diagnostics; this is not the canonical reset-pose file.
python scripts/tools/save_reset_pose.py --port can1 --handedness right \
    --output configs/o10_right_reset_pose.json

# Read current dual-arm joints and export two legacy JSON files, one per side.
python scripts/tools/save_dual_reset_pose.py \
    --left-port can0 --right-port can1 \
    --left-output configs/o10_left_reset_pose.json \
    --right-output configs/o10_right_reset_pose.json

# Export per-side per-gesture reset files for each gesture, default pinch + tripod.
python scripts/tools/save_gesture_reset_poses.py
python scripts/tools/save_gesture_reset_poses.py --gesture pinch

# Move arm/hand to poses from the canonical JSON, or only read current poses.
python scripts/tools/set_pose.py --from-json configs/reset_poses/o10_dual_reset.json
python scripts/tools/set_pose.py --arm 0 0 0 0 0 0
python scripts/tools/set_pose.py --read-only

# Check whether tactile channels in a recorded dataset contain data.
python scripts/tools/check_tactile_success.py --dataset.root <dataset_dir>

# Convert a LeRobot dataset to openpi training format.
python scripts/tools/convert_lerobot_to_openpi.py --input <lerobot_dir> --output <openpi_dir>
```

> `save_reset_pose.py` / `save_dual_reset_pose.py` / `save_gesture_reset_poses.py` output legacy `groups.arm / groups.hand` format and must not directly overwrite `configs/reset_poses/o10_dual_reset.json`. Manually merge new joint values into the canonical JSON fields `arm.<side>` / `gestures.<name>.<side>.open|closed`.

## Tests And Checks

```bash
# full Python regression suite
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests -q

# common focused checks
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_dual_arm_config.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_infer_save_path.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_single_arm_o10_trigger_gate.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_dual_arm_o10_trigger_gate.py -q
```

The current full regression suite should be `103 passed, 1 skipped`. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` avoids interference from ROS or external pytest plugins.

## Troubleshooting

- OpenCV preview window error: in headless environments, set `display_data` or `run.display_data` to `false`.
- `model_path` does not exist: check `infer.model_path` in the infer YAML. It must point to a `.../pretrained_model` directory.
- Inference input dimension mismatch: confirm infer YAML `include_eef_pose`, `tactile_mode`, and camera keys match the record YAML used for training.
- Top USB camera reads are unstable: confirm the camera config includes `fourcc: MJPG`.
- A camera is missing in control/infer: enable `robot.allow_camera_read_failures: true`; the program skips cameras that fail startup.
- A camera fails during recording: do not rely on tolerance. Fix the camera and record again to avoid all-zero or stale frames in the dataset.
- Glove cannot connect: confirm HDService is running, HDWeb shows the paired glove, and YAML `handedness` is correct.
- Hand CANFD timeout: check hand power, USB-CANFD cable, and `channel_id`.
- Dual-arm visual left/right confusion: when facing the robot, the robot's own left arm appears on your visual right. Use single-left/single-right scripts to confirm which hardware arm maps to `can0` / `can1`.
- Recording directory already exists: change `dataset.repo_id` or delete the old empty directory.
