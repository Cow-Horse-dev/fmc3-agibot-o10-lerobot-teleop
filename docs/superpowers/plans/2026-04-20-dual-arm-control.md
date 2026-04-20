# O10 双臂控制实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 O10 机器人新增双臂控制类型，支持左臂单独、右臂单独、双臂同时三种模式。

**Architecture:** 新建 `pico_leader_dual_arm_agibot_o10` 和 `pico_follower_dual_arm_agibot_o10` 两个类型，内部组合两个单臂实例。共用一个 WebRTC 连接同时读取左右腕带位姿，分别驱动两只臂和两只手。

**Tech Stack:** Python 3, LeRobot type system, airbot_hardware_py, OmniHand SDK, WebRTC (Pico wrist)

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|------|------|
| `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10/__init__.py` | 导出双臂 follower 类 |
| `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10/config_pico_follower_dual_arm_agibot_o10.py` | 双臂 follower 配置 dataclass |
| `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10/airbot_pico_follower_dual_arm_agibot_o10.py` | 双臂 follower 实现 |
| `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/__init__.py` | 导出双臂 leader 类 |
| `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/config_pico_leader_dual_arm_agibot_o10.py` | 双臂 leader 配置 dataclass |
| `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/pico_leader_dual_arm_agibot_o10.py` | 双臂 leader 实现 |
| `configs/o10_left_control.yaml` | 左臂单独控制配置 |
| `configs/o10_left_record.yaml` | 左臂单独录制配置 |
| `configs/o10_left_replay.yaml` | 左臂单独回放配置 |
| `configs/o10_left_infer.yaml` | 左臂单独推理配置 |
| `configs/o10_dual_control.yaml` | 双臂控制配置 |
| `configs/o10_dual_record.yaml` | 双臂录制配置 |
| `configs/o10_dual_replay.yaml` | 双臂回放配置 |
| `configs/o10_dual_infer.yaml` | 双臂推理配置 |
| `scripts/control_o10_left.sh` | 左臂控制脚本 |
| `scripts/record_o10_left.sh` | 左臂录制脚本 |
| `scripts/replay_o10_left.sh` | 左臂回放脚本 |
| `scripts/infer_o10_left.sh` | 左臂推理脚本 |
| `scripts/control_o10_dual.sh` | 双臂控制脚本 |
| `scripts/record_o10_dual.sh` | 双臂录制脚本 |
| `scripts/replay_o10_dual.sh` | 双臂回放脚本 |
| `scripts/infer_o10_dual.sh` | 双臂推理脚本 |
| `qiuzhi/tests/test_dual_arm_config.py` | 双臂配置解析测试 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/utils.py` | 注册新的双臂 follower 类型 |
| `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/utils.py` | 注册新的双臂 leader 类型 |

---

## Task 1: 双臂 Follower 配置类

**Files:**
- Create: `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10/__init__.py`
- Create: `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10/config_pico_follower_dual_arm_agibot_o10.py`

- [ ] **Step 1: 创建配置 dataclass**

```python
# config_pico_follower_dual_arm_agibot_o10.py
from dataclasses import dataclass, field
from typing import List

from lerobot.cameras.configs import CameraConfig
from lerobot.robots.config import RobotConfig


@dataclass
class DualArmSideConfig:
    port: str = "can0"
    handedness: str = "right"
    channel_mode: str = "multiChannel"
    device_id: int = 1
    canfd_id: int = 0
    channel_id: int | None = None
    arm_reset_joints_path: str | None = None
    hand_reset_joints_path: str | None = None


@RobotConfig.register_subclass("pico_follower_dual_arm_agibot_o10")
@dataclass
class PicoFollowerDualArmAgibotO10Config(RobotConfig):
    left: dict = field(default_factory=dict)
    right: dict = field(default_factory=dict)
    disable_torque_on_disconnect: bool = True
    max_relative_target: List[float] = field(default_factory=lambda: [0.1, 0.1])
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
    use_degrees: bool = False
    arm_joints_num: int = 7
    serial_freq: int = 500
```

- [ ] **Step 2: 创建 __init__.py**

```python
# __init__.py
from .config_pico_follower_dual_arm_agibot_o10 import (
    PicoFollowerDualArmAgibotO10Config,
)
from .airbot_pico_follower_dual_arm_agibot_o10 import (
    PicoFollowerDualArmAgibotO10,
)

__all__ = [
    "PicoFollowerDualArmAgibotO10Config",
    "PicoFollowerDualArmAgibotO10",
]
```

- [ ] **Step 3: Commit**

```bash
git add qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10/
git commit -m "feat: add dual-arm follower config class"
```

---

## Task 2: 双臂 Follower 实现

**Files:**
- Create: `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10/airbot_pico_follower_dual_arm_agibot_o10.py`

- [ ] **Step 1: 实现双臂 Robot 类**

核心逻辑：内部持有两个 arm (`ah.Play`) + 两个 hand (`AgibotO10Hand`)，分别连接 left/right 的 CAN 口。

关键方法：
- `__init__`: 从 config.left / config.right 字典解析参数，创建两套 arm+hand
- `connect()`: 依次初始化左臂、右臂、左手、右手
- `get_observation()`: 返回 46D（left_arm[6] + left_hand[10] + left_eef[7] + right_arm[6] + right_hand[10] + right_eef[7]）+ 相机
- `send_action()`: 接收 32D action，前 16D 给左臂/手，后 16D 给右臂/手
- `return_zero()`: 两臂同时回到各自的 reset 位置
- `disconnect()`: 依次断开两臂两手

Feature names 使用前缀区分：
- `left.joint1.pos` ... `left.joint6.pos`, `left.thumb_cm_roll.pos` ...
- `right.joint1.pos` ... `right.joint6.pos`, `right.thumb_cm_roll.pos` ...
- `left.pose.x` ... `left.quaternion.qw`
- `right.pose.x` ... `right.quaternion.qw`

```python
# 关键常量定义
DUAL_ARM_FEATURE_NAMES = tuple(
    f"left.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES
) + tuple(
    f"left.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES
)

DUAL_ARM_STATE_FEATURE_NAMES = tuple(
    f"left.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES
) + tuple(
    f"left.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES
) + tuple(
    f"left.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES
) + tuple(
    f"right.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES
)
```

- [ ] **Step 2: Commit**

```bash
git add qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10/
git commit -m "feat: implement dual-arm follower robot class"
```

---

## Task 3: 双臂 Leader 配置类

**Files:**
- Create: `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/__init__.py`
- Create: `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/config_pico_leader_dual_arm_agibot_o10.py`

- [ ] **Step 1: 创建配置 dataclass**

```python
# config_pico_leader_dual_arm_agibot_o10.py
from dataclasses import dataclass, field
from typing import List

from lerobot.cameras.configs import CameraConfig
from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("pico_leader_dual_arm_agibot_o10")
@dataclass
class PicoLeaderDualArmAgibotO10Config(TeleoperatorConfig):
    vr_pose_port: int = 8000
    vr_ctrl_port: int = 8001
    vr_device: str = "pico_wrist"
    enable_hand: bool = True
    left: dict = field(default_factory=dict)
    right: dict = field(default_factory=dict)
    disable_torque_on_disconnect: bool = True
    max_relative_target: List[float] = field(default_factory=lambda: [0.1, 0.1])
    cameras: dict[str, CameraConfig] = field(default_factory=dict)
    use_degrees: bool = False
    arm_joints_num: int = 7
    serial_freq: int = 500
```

- [ ] **Step 2: 创建 __init__.py**

```python
# __init__.py
from .config_pico_leader_dual_arm_agibot_o10 import (
    PicoLeaderDualArmAgibotO10Config,
)
from .pico_leader_dual_arm_agibot_o10 import (
    PicoLeaderDualArmAgibotO10,
)

__all__ = [
    "PicoLeaderDualArmAgibotO10Config",
    "PicoLeaderDualArmAgibotO10",
]
```

- [ ] **Step 3: Commit**

```bash
git add qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/
git commit -m "feat: add dual-arm leader config class"
```

---

## Task 4: 双臂 Leader 实现

**Files:**
- Create: `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/pico_leader_dual_arm_agibot_o10.py`

- [ ] **Step 1: 实现双臂 Teleoperator 类**

核心逻辑：继承 `PicoLeaderSingleArmEEF`，复用其 WebRTC 连接（同一组端口同时接收 left_wrist 和 right_wrist 数据）。内部持有两个 `AgibotO10GloveTeleoperator`（左右手套）和两套 IK 求解器。

关键方法：
- `__init__`: 创建两个 glove teleoperator，两套 reset store，两套 LPF
- `connect()`: 启动 WebRTC 事件线程，初始化两只手套
- `get_joint_pos()`: 返回 32D（left_arm[6] + left_hand[10] + right_arm[6] + right_hand[10]）
- `get_action()`: 调用 `get_joint_pos()` 构建 action dict
- `reset_pose()`: 两臂各自回到 reset 位置
- `_select_control_pose()`: 重写为同时返回左右两个位姿

WebRTC 数据流：
- `self.left_info` → 左臂 IK（`wrist_pose_source: left`）
- `self.right_info` → 右臂 IK（`wrist_pose_source: right`）

手套触发逻辑：
- 左手手套由 `RTr`（右扳机）触发
- 右手手套由 `LTr`（左扳机）触发
- 双臂模式下两个扳机各自独立控制对应手

- [ ] **Step 2: Commit**

```bash
git add qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/
git commit -m "feat: implement dual-arm leader teleoperator class"
```

---

## Task 5: 注册新类型到工厂函数

**Files:**
- Modify: `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/utils.py`
- Modify: `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/utils.py`

- [ ] **Step 1: 在 robots/utils.py 添加双臂 follower**

在 `pico_follower_single_arm_agibot_o10` 分支后面添加：

```python
    elif config.type == "pico_follower_dual_arm_agibot_o10":
        from .pico_follower_dual_arm_agibot_o10 import (
            PicoFollowerDualArmAgibotO10,
        )

        return PicoFollowerDualArmAgibotO10(config)
```

- [ ] **Step 2: 在 teleoperators/utils.py 添加双臂 leader**

在 `pico_leader_single_arm_agibot_o10` 分支后面添加：

```python
    elif config.type == "pico_leader_dual_arm_agibot_o10":
        from .pico_leader_dual_arm_agibot_o10 import PicoLeaderDualArmAgibotO10

        return PicoLeaderDualArmAgibotO10(config)
```

- [ ] **Step 3: Commit**

```bash
git add qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/utils.py
git add qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/utils.py
git commit -m "feat: register dual-arm types in factory functions"
```

---

## Task 6: 左臂配置文件

**Files:**
- Create: `configs/o10_left_control.yaml`
- Create: `configs/o10_left_record.yaml`
- Create: `configs/o10_left_replay.yaml`
- Create: `configs/o10_left_infer.yaml`

- [ ] **Step 1: 创建左臂 control 配置**

镜像 `o10_right_control.yaml`，修改：
- `teleop.handedness: left`
- `teleop.wrist_pose_source: left`
- `teleop.id: pico_left`
- `teleop.arm_reset_joints_path` / `hand_reset_joints_path` → `o10_left_reset_pose.json`
- `robot.port: can1`
- `robot.handedness: left`
- `robot.id: o10_left`
- `robot.arm_reset_joints_path` / `hand_reset_joints_path` → `o10_left_reset_pose.json`

- [ ] **Step 2: 创建左臂 record/replay/infer 配置**

同样镜像对应的 right 配置，修改 handedness、port、reset paths。

- [ ] **Step 3: Commit**

```bash
git add configs/o10_left_*.yaml
git commit -m "feat: add left-arm-only config files"
```

---

## Task 7: 双臂配置文件

**Files:**
- Create: `configs/o10_dual_control.yaml`
- Create: `configs/o10_dual_record.yaml`
- Create: `configs/o10_dual_replay.yaml`
- Create: `configs/o10_dual_infer.yaml`

- [ ] **Step 1: 创建双臂 control 配置**

按设计文档中的 `o10_dual_control.yaml` 示例创建。

- [ ] **Step 2: 创建双臂 record 配置**

在 control 基础上添加 `run` 和 `dataset` 节（参考 `o10_right_record.yaml`）。

- [ ] **Step 3: 创建双臂 replay/infer 配置**

参考对应的 right 版本，使用双臂类型名。

- [ ] **Step 4: Commit**

```bash
git add configs/o10_dual_*.yaml
git commit -m "feat: add dual-arm config files"
```

---

## Task 8: 启动脚本

**Files:**
- Create: `scripts/control_o10_left.sh`
- Create: `scripts/record_o10_left.sh`
- Create: `scripts/replay_o10_left.sh`
- Create: `scripts/infer_o10_left.sh`
- Create: `scripts/control_o10_dual.sh`
- Create: `scripts/record_o10_dual.sh`
- Create: `scripts/replay_o10_dual.sh`
- Create: `scripts/infer_o10_dual.sh`

- [ ] **Step 1: 创建左臂脚本**

格式与 `control_o10_right.sh` 一致，指向 `configs/o10_left_*.yaml`。

示例 `scripts/control_o10_left.sh`：
```bash
#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common_env.sh"

cd "$arm_hand_teleop_repo_root"

"$arm_hand_teleop_python_bin" \
  "$arm_hand_teleop_repo_root/run_lerobot_play.py" control \
  --config_path "$arm_hand_teleop_repo_root/configs/o10_left_control.yaml" \
  "$@"
```

- [ ] **Step 2: 创建双臂脚本**

同上，指向 `configs/o10_dual_*.yaml`。

- [ ] **Step 3: 设置可执行权限并 commit**

```bash
chmod +x scripts/control_o10_left.sh scripts/record_o10_left.sh scripts/replay_o10_left.sh scripts/infer_o10_left.sh
chmod +x scripts/control_o10_dual.sh scripts/record_o10_dual.sh scripts/replay_o10_dual.sh scripts/infer_o10_dual.sh
git add scripts/*_o10_left.sh scripts/*_o10_dual.sh
git commit -m "feat: add left-arm and dual-arm launch scripts"
```

---

## Task 9: 单元测试

**Files:**
- Create: `qiuzhi/tests/test_dual_arm_config.py`

- [ ] **Step 1: 编写配置解析测试**

```python
import pytest
import yaml

def test_dual_control_yaml_parses():
    with open("configs/o10_dual_control.yaml") as f:
        config = yaml.safe_load(f)
    assert config["teleop"]["type"] == "pico_leader_dual_arm_agibot_o10"
    assert config["robot"]["type"] == "pico_follower_dual_arm_agibot_o10"
    assert config["robot"]["left"]["port"] == "can1"
    assert config["robot"]["right"]["port"] == "can0"
    assert config["teleop"]["left"]["handedness"] == "left"
    assert config["teleop"]["right"]["handedness"] == "right"

def test_left_control_yaml_parses():
    with open("configs/o10_left_control.yaml") as f:
        config = yaml.safe_load(f)
    assert config["teleop"]["type"] == "pico_leader_single_arm_agibot_o10"
    assert config["robot"]["type"] == "pico_follower_single_arm_agibot_o10"
    assert config["robot"]["port"] == "can1"
    assert config["teleop"]["handedness"] == "left"

def test_dual_arm_feature_dimensions():
    from lerobot_play.utils.agibot_o10 import (
        AGIBOT_O10_ARM_FEATURE_NAMES,
        AGIBOT_O10_HAND_FEATURE_NAMES,
        AGIBOT_O10_POSE_FEATURE_NAMES,
    )
    action_dim = 2 * (len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES))
    state_dim = 2 * (len(AGIBOT_O10_ARM_FEATURE_NAMES) + len(AGIBOT_O10_HAND_FEATURE_NAMES) + len(AGIBOT_O10_POSE_FEATURE_NAMES))
    assert action_dim == 32
    assert state_dim == 46
```

- [ ] **Step 2: 运行测试**

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_dual_arm_config.py -v
```

- [ ] **Step 3: Commit**

```bash
git add qiuzhi/tests/test_dual_arm_config.py
git commit -m "test: add dual-arm config parsing tests"
```
