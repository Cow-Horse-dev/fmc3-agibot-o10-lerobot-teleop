# Dual-Arm Control Design

## Goal

Extend the O10 single-arm teleoperation system to support three control modes:
1. Left arm only
2. Right arm only (existing)
3. Both arms simultaneously (dual)

## Hardware Setup

- Pico headset tracks both wrists via a single WebRTC connection (ports 8000/8001)
- Left arm: CAN port `can1`, OmniHand channel_id auto → 0
- Right arm: CAN port `can0`, OmniHand channel_id auto → 1
- Both arms: `device_id: 1`, `canfd_id: 0`, `channel_mode: multiChannel`
- Udexreal gloves: one per hand, data via HDService UDP

## Approach

New dual-arm types registered in the LeRobot type system, internally composing two single-arm instances. Single-arm configs remain unchanged.

## New Types

### `pico_leader_dual_arm_agibot_o10` (Teleoperator)

- Inherits from `PicoLeaderSingleArmEEF` (reuses WebRTC connection + event thread)
- Holds two `AgibotO10GloveTeleoperator` instances (left/right gloves)
- WebRTC data parsed for both `left_wrist` and `right_wrist` simultaneously
- Each wrist pose drives independent IK solving
- `get_action()` returns 32D: left_arm[6] + left_hand[10] + right_arm[6] + right_hand[10]

### `pico_follower_dual_arm_agibot_o10` (Robot)

- Holds two `ah.Play` instances (left/right arms) + two `AgibotO10Hand` instances
- `send_action()` accepts 32D action, splits and dispatches to each arm/hand
- `get_observation()` returns 46D state: left_arm[6] + left_hand[10] + left_eef_pose[7] + right_arm[6] + right_hand[10] + right_eef_pose[7]
- Independent connect/disconnect per arm; one failure does not block the other

## Config Classes

```python
@TeleoperatorConfig.register_subclass("pico_leader_dual_arm_agibot_o10")
@dataclass
class PicoLeaderDualArmAgibotO10Config(TeleoperatorConfig):
    vr_pose_port: int = 8000
    vr_ctrl_port: int = 8001
    vr_device: str = "pico_wrist"
    enable_hand: bool = True
    left: dict = field(default_factory=dict)
    right: dict = field(default_factory=dict)
```

```python
@RobotConfig.register_subclass("pico_follower_dual_arm_agibot_o10")
@dataclass
class PicoFollowerDualArmAgibotO10Config(RobotConfig):
    left: dict = field(default_factory=dict)
    right: dict = field(default_factory=dict)
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
```

`left` / `right` sub-dicts contain per-arm parameters:
- Leader: `handedness`, `wrist_pose_source`, `arm_reset_joints_path`, `hand_reset_joints_path`
- Follower: `port`, `handedness`, `channel_mode`, `device_id`, `canfd_id`, `channel_id`, `arm_reset_joints_path`, `hand_reset_joints_path`

## File Layout

```
qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/
├── teleoperators/
│   └── pico_leader_dual_arm_agibot_o10/
│       ├── __init__.py
│       ├── config_pico_leader_dual_arm_agibot_o10.py
│       └── pico_leader_dual_arm_agibot_o10.py
└── robots/
    └── pico_follower_dual_arm_agibot_o10/
        ├── __init__.py
        ├── config_pico_follower_dual_arm_agibot_o10.py
        └── airbot_pico_follower_dual_arm_agibot_o10.py
```

## Configuration Files

Three sets of YAML configs for each mode (control, record, replay, infer):

| Mode | Config file | teleop type | robot type |
|------|-------------|-------------|------------|
| Left only | `o10_left_*.yaml` | `pico_leader_single_arm_agibot_o10` | `pico_follower_single_arm_agibot_o10` |
| Right only | `o10_right_*.yaml` | `pico_leader_single_arm_agibot_o10` | `pico_follower_single_arm_agibot_o10` |
| Dual | `o10_dual_*.yaml` | `pico_leader_dual_arm_agibot_o10` | `pico_follower_dual_arm_agibot_o10` |

### Dual control config example (`o10_dual_control.yaml`)

```yaml
teleop:
  type: pico_leader_dual_arm_agibot_o10
  id: pico_dual
  vr_pose_port: 8000
  vr_ctrl_port: 8001
  vr_device: pico_wrist
  enable_hand: true
  left:
    handedness: left
    wrist_pose_source: left
    arm_reset_joints_path: ~/workspace/arm-hand-teleop/configs/o10_left_reset_pose.json
    hand_reset_joints_path: ~/workspace/arm-hand-teleop/configs/o10_left_reset_pose.json
  right:
    handedness: right
    wrist_pose_source: right
    arm_reset_joints_path: ~/workspace/arm-hand-teleop/configs/o10_right_reset_pose.json
    hand_reset_joints_path: ~/workspace/arm-hand-teleop/configs/o10_right_reset_pose.json

robot:
  type: pico_follower_dual_arm_agibot_o10
  id: o10_dual
  left:
    port: can1
    handedness: left
    channel_mode: multiChannel
    device_id: 1
    canfd_id: 0
    channel_id: null
  right:
    port: can0
    handedness: right
    channel_mode: multiChannel
    device_id: 1
    canfd_id: 0
    channel_id: null
  cameras:
    top:
      type: opencv
      index_or_path: /dev/v4l/by-id/usb-LRCP_500W_LRCP_500W_200901010001-video-index0
      width: 640
      height: 480
      fps: 30
      rotation: NO_ROTATION

fps: 30
display_data: true
```

## Scripts

New shell scripts:
- `scripts/control_o10_left.sh`
- `scripts/control_o10_dual.sh`
- `scripts/record_o10_left.sh`
- `scripts/record_o10_dual.sh`
- `scripts/replay_o10_left.sh`
- `scripts/replay_o10_dual.sh`
- `scripts/infer_o10_left.sh`
- `scripts/infer_o10_dual.sh`

Each follows the same pattern as existing `*_right.sh` scripts, pointing to the corresponding YAML config.

## Dataset Dimensions

| Mode | Action dim | State dim |
|------|-----------|-----------|
| Single arm | 16D (arm[6] + hand[10]) | 23D (arm[6] + hand[10] + eef_pose[7]) |
| Dual arm | 32D (left_arm[6] + left_hand[10] + right_arm[6] + right_hand[10]) | 46D (left_arm[6] + left_hand[10] + left_eef[7] + right_arm[6] + right_hand[10] + right_eef[7]) |

## Left-Only Config

`o10_left_control.yaml` is a mirror of the existing right config with:
- `handedness: left`
- `wrist_pose_source: left`
- `port: can1`
- `channel_id: null` (auto → 0)
- Reset paths point to `o10_left_reset_pose.json`

No new Python types needed for left-only — reuses existing `pico_leader_single_arm_agibot_o10` / `pico_follower_single_arm_agibot_o10`.

## Testing

- Unit tests for config parsing (dual YAML → correct left/right sub-configs)
- Integration test: verify `get_action()` returns 32D, `get_observation()` returns 46D (stubbed hardware)
- Manual validation: dual control with actual hardware before merging

