# 双臂控制设计

## 目标

扩展 O10 单臂遥操作系统，支持三种控制模式：
1. 仅左臂
2. 仅右臂（已有）
3. 双臂同时控制

## 硬件配置

- Pico 头显通过单个 WebRTC 连接同时追踪两只手腕（端口 8000/8001）
- 左臂：CAN 口 `can1`，OmniHand channel_id 自动 → 0
- 右臂：CAN 口 `can0`，OmniHand channel_id 自动 → 1
- 两臂共用：`device_id: 1`，`canfd_id: 0`，`channel_mode: multiChannel`
- 宇叠手套：左右各一只，数据通过 HDService UDP 传输

## 方案

在 LeRobot 类型系统中注册新的双臂类型，内部组合两个单臂实例。现有单臂配置不受影响。

## 新增类型

### `pico_leader_dual_arm_agibot_o10`（Teleoperator）

- 继承 `PicoLeaderSingleArmEEF`（复用 WebRTC 连接和事件线程）
- 持有两个 `AgibotO10GloveTeleoperator` 实例（左右手套）
- WebRTC 数据同时解析 `left_wrist` 和 `right_wrist` 位姿
- 每只手腕位姿独立驱动 IK 求解
- `get_action()` 返回 32D：left_arm[6] + left_hand[10] + right_arm[6] + right_hand[10]

### `pico_follower_dual_arm_agibot_o10`（Robot）

- 持有两个 `ah.Play` 实例（左右臂）+ 两个 `AgibotO10Hand` 实例
- `send_action()` 接收 32D action，拆分后分别下发到各臂/手
- `get_observation()` 返回 46D state：left_arm[6] + left_hand[10] + left_eef_pose[7] + right_arm[6] + right_hand[10] + right_eef_pose[7]
- 左右臂独立 connect/disconnect；一个失败不阻塞另一个

## Config 类

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

`left` / `right` 子字典包含各臂参数：
- Leader 端：`handedness`、`wrist_pose_source`、`arm_reset_joints_path`、`hand_reset_joints_path`
- Follower 端：`port`、`handedness`、`channel_mode`、`device_id`、`canfd_id`、`channel_id`、`arm_reset_joints_path`、`hand_reset_joints_path`

## 文件布局

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

## 配置文件

每种模式（control、record、replay、infer）各三套 YAML：

| 模式 | 配置文件 | teleop 类型 | robot 类型 |
|------|----------|-------------|------------|
| 仅左臂 | `o10_left_*.yaml` | `pico_leader_single_arm_agibot_o10` | `pico_follower_single_arm_agibot_o10` |
| 仅右臂 | `o10_right_*.yaml` | `pico_leader_single_arm_agibot_o10` | `pico_follower_single_arm_agibot_o10` |
| 双臂 | `o10_dual_*.yaml` | `pico_leader_dual_arm_agibot_o10` | `pico_follower_dual_arm_agibot_o10` |

### 双臂控制配置示例（`o10_dual_control.yaml`）

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

## 启动脚本

新增 shell 脚本：
- `scripts/control_o10_left.sh`
- `scripts/control_o10_dual.sh`
- `scripts/record_o10_left.sh`
- `scripts/record_o10_dual.sh`
- `scripts/replay_o10_left.sh`
- `scripts/replay_o10_dual.sh`
- `scripts/infer_o10_left.sh`
- `scripts/infer_o10_dual.sh`

每个脚本与现有 `*_right.sh` 格式一致，指向对应的 YAML 配置。

## 数据集维度

| 模式 | Action 维度 | State 维度 |
|------|------------|------------|
| 单臂 | 16D（arm[6] + hand[10]） | 23D（arm[6] + hand[10] + eef_pose[7]） |
| 双臂 | 32D（left_arm[6] + left_hand[10] + right_arm[6] + right_hand[10]） | 46D（left_arm[6] + left_hand[10] + left_eef[7] + right_arm[6] + right_hand[10] + right_eef[7]） |

## 仅左臂配置

`o10_left_control.yaml` 是现有右臂配置的镜像，修改点：
- `handedness: left`
- `wrist_pose_source: left`
- `port: can1`
- `channel_id: null`（自动 → 0）
- 复位路径指向 `o10_left_reset_pose.json`

仅左臂不需要新 Python 类型 — 复用现有 `pico_leader_single_arm_agibot_o10` / `pico_follower_single_arm_agibot_o10`。

## 测试

- 单元测试：配置解析（双臂 YAML → 正确的左右子配置）
- 集成测试：验证 `get_action()` 返回 32D，`get_observation()` 返回 46D（mock 硬件）
- 手动验证：实际硬件双臂控制，合并前完成

