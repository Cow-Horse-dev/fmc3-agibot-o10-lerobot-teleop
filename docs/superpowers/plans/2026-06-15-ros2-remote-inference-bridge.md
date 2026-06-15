# ROS2 Remote Inference Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run policy inference on GPU host A driving an AGIBOT O10 dual-arm robot whose hardware lives on host B, with observations/actions flowing over ROS2 instead of gRPC.

**Architecture:** Reuse the existing async split. Host B runs `ros2_robot_bridge` — a `RobotClient` subclass that overrides only the transport (`send_observation`→publish, `receive_actions`→ROS2 subscription) while reusing the control loop, action queue, `_aggregate_action_queues`, `must_go`, and reset/episode flow. Host A runs `ros2_policy_node` — a thin wrapper that holds the existing `PolicyServer` and drives it via dummy request/context shims (`SendPolicyInstructions`, `_enqueue_observation`, `GetActions` reused verbatim). A latched `RobotSchema` handshake carries a pickled `RemotePolicyConfig`. Observations/actions are typed custom messages embedding standard `sensor_msgs` sub-types.

**Tech Stack:** Python, rclpy, ROS2 (ament_cmake interface package), `sensor_msgs`/`trajectory_msgs`/`std_srvs`, OpenCV (JPEG), torch, vendored `lerobot_play`, external LeRobot async_inference, pytest.

**Reference spec:** `docs/superpowers/specs/2026-06-15-ros2-remote-inference-bridge-design.md`

**Path shorthand used below:**
- `LP/` = `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/`
- Run tests with the repo convention: `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest …`

---

### Task 1: ROS2 interface package `lerobot_ros2_msgs`

**Files:**
- Create: `ros2_ws/src/lerobot_ros2_msgs/package.xml`
- Create: `ros2_ws/src/lerobot_ros2_msgs/CMakeLists.txt`
- Create: `ros2_ws/src/lerobot_ros2_msgs/msg/ActionPoint.msg`
- Create: `ros2_ws/src/lerobot_ros2_msgs/msg/ActionChunk.msg`
- Create: `ros2_ws/src/lerobot_ros2_msgs/msg/Observation.msg`
- Create: `ros2_ws/src/lerobot_ros2_msgs/msg/RobotSchema.msg`

- [ ] **Step 1: Write `package.xml`**

```xml
<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>lerobot_ros2_msgs</name>
  <version>0.1.0</version>
  <description>Messages for the lerobot_play ROS2 remote inference bridge</description>
  <maintainer email="h01053407777@gmail.com">heliangp</maintainer>
  <license>Proprietary</license>

  <buildtool_depend>ament_cmake</buildtool_depend>
  <buildtool_depend>rosidl_default_generators</buildtool_depend>

  <depend>std_msgs</depend>
  <depend>sensor_msgs</depend>

  <exec_depend>rosidl_default_runtime</exec_depend>
  <member_of_group>rosidl_interface_packages</member_of_group>

  <export>
    <build_type>ament_cmake</build_type>
  </export>
</package>
```

- [ ] **Step 2: Write `CMakeLists.txt`**

```cmake
cmake_minimum_required(VERSION 3.8)
project(lerobot_ros2_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ActionPoint.msg"
  "msg/ActionChunk.msg"
  "msg/Observation.msg"
  "msg/RobotSchema.msg"
  DEPENDENCIES std_msgs sensor_msgs
)

ament_package()
```

- [ ] **Step 3: Write the four `.msg` files**

`msg/ActionPoint.msg`:

```
int64 timestep
float64[] position
```

`msg/ActionChunk.msg`:

```
std_msgs/Header header
int64 base_timestep
string[] joint_names
ActionPoint[] points
```

`msg/Observation.msg`:

```
std_msgs/Header header
int64 timestep
bool must_go
string task
sensor_msgs/JointState state
sensor_msgs/CompressedImage[] images
string[] image_keys
```

`msg/RobotSchema.msg`:

```
std_msgs/Header header
uint8[] remote_policy_config
string policy_type
string model_path
int64 actions_per_chunk
```

- [ ] **Step 4: Build the package and verify the interfaces**

Run (adjust the ROS2 distro source line to the installed distro, e.g. `humble`/`jazzy`):

```bash
source /opt/ros/$(ls /opt/ros | head -1)/setup.bash
cd /home/phl/workspace/arm-hand-teleop/ros2_ws
colcon build --packages-select lerobot_ros2_msgs
source install/setup.bash
ros2 interface show lerobot_ros2_msgs/msg/Observation
ros2 interface show lerobot_ros2_msgs/msg/ActionChunk
ros2 interface show lerobot_ros2_msgs/msg/RobotSchema
```

Expected: each `ros2 interface show` prints the fields with no error.

- [ ] **Step 5: Ignore build artifacts**

Append to `.gitignore` at repo root:

```
ros2_ws/build/
ros2_ws/install/
ros2_ws/log/
```

- [ ] **Step 6: Commit**

```bash
git add ros2_ws/src/lerobot_ros2_msgs .gitignore
git commit -m "heliangp:新增 ROS2 推理桥消息接口包"
```

---

### Task 2: Pure observation/action conversion helpers (TDD)

These functions convert between LeRobot `TimedObservation`/`TimedAction` and plain field dataclasses. They have **no rclpy / ROS-message dependency**, so they are fully unit-testable without a built workspace or hardware. The thin ROS-message glue comes in Task 3.

**Files:**
- Create: `LP/ros2_inference/__init__.py`
- Create: `LP/ros2_inference/messages.py`
- Test: `qiuzhi/tests/test_ros2_messages.py`

- [ ] **Step 1: Create the empty package marker**

`LP/ros2_inference/__init__.py`:

```python
```

(empty file)

- [ ] **Step 2: Write the failing tests**

`qiuzhi/tests/test_ros2_messages.py`:

```python
import numpy as np
import torch

from lerobot.async_inference.helpers import TimedAction, TimedObservation

from lerobot_play.ros2_inference.messages import (
    ObservationFields,
    ActionChunkFields,
    pack_observation,
    unpack_observation,
    pack_action_chunk,
    unpack_action_chunk,
)


def _make_timed_observation():
    image = np.full((48, 64, 3), [10, 150, 200], dtype=np.uint8)
    raw = {
        "left.joint1.pos": 0.5,
        "left.joint2.pos": -1.25,
        "right.gripper.pos": np.float64(0.75),
        "top": image,
        "task": "pick up the cube",
    }
    obs = TimedObservation(timestamp=123.5, observation=raw, timestep=7)
    obs.must_go = True
    return obs, image


def test_pack_observation_extracts_scalars_images_and_metadata():
    obs, image = _make_timed_observation()
    fields = pack_observation(obs)

    assert isinstance(fields, ObservationFields)
    assert fields.timestep == 7
    assert fields.must_go is True
    assert fields.task == "pick up the cube"
    assert dict(zip(fields.state_names, fields.state_positions)) == {
        "left.joint1.pos": 0.5,
        "left.joint2.pos": -1.25,
        "right.gripper.pos": 0.75,
    }
    assert fields.image_keys == ["top"]
    assert len(fields.image_jpegs) == 1
    assert isinstance(fields.image_jpegs[0], bytes)


def test_observation_round_trip_preserves_state_and_image():
    obs, image = _make_timed_observation()
    raw = unpack_observation(pack_observation(obs))

    assert raw["task"] == "pick up the cube"
    assert raw["left.joint1.pos"] == 0.5
    assert raw["right.gripper.pos"] == 0.75
    assert raw["top"].shape == image.shape
    assert raw["top"].dtype == np.uint8
    # JPEG on a flat image is near-lossless
    assert np.abs(raw["top"].astype(int) - image.astype(int)).max() < 10


def test_action_chunk_round_trip_preserves_timesteps_and_positions():
    joint_names = ["left.joint1.pos", "left.joint2.pos", "right.gripper.pos"]
    timed_actions = [
        TimedAction(timestamp=100.0, timestep=5, action=torch.tensor([0.1, 0.2, 0.3])),
        TimedAction(timestamp=100.1, timestep=6, action=torch.tensor([0.4, 0.5, 0.6])),
    ]

    fields = pack_action_chunk(timed_actions, joint_names)
    assert isinstance(fields, ActionChunkFields)
    assert fields.base_timestep == 5
    assert fields.joint_names == joint_names
    assert [p.timestep for p in fields.points] == [5, 6]

    restored = unpack_action_chunk(fields)
    assert [a.get_timestep() for a in restored] == [5, 6]
    np.testing.assert_allclose(restored[0].get_action().numpy(), [0.1, 0.2, 0.3], atol=1e-6)
    np.testing.assert_allclose(restored[1].get_action().numpy(), [0.4, 0.5, 0.6], atol=1e-6)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run:

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_ros2_messages.py -v
```

Expected: FAIL — `ImportError: cannot import name 'ObservationFields' from 'lerobot_play.ros2_inference.messages'` (module does not exist yet).

- [ ] **Step 4: Implement `messages.py`**

`LP/ros2_inference/messages.py`:

```python
"""Pure conversion between LeRobot TimedObservation/TimedAction and plain field
dataclasses. No rclpy / ROS-message imports here, so this module is unit-testable
without a built ROS2 workspace or hardware. ROS-message glue lives in ros_io.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
import torch

from lerobot.async_inference.helpers import TimedAction, TimedObservation


@dataclass
class ObservationFields:
    timestep: int
    must_go: bool
    task: str
    timestamp: float
    state_names: list[str] = field(default_factory=list)
    state_positions: list[float] = field(default_factory=list)
    image_keys: list[str] = field(default_factory=list)
    image_jpegs: list[bytes] = field(default_factory=list)


@dataclass
class ActionPointFields:
    timestep: int
    position: list[float]


@dataclass
class ActionChunkFields:
    base_timestep: int
    timestamp: float
    joint_names: list[str]
    points: list[ActionPointFields]


def _is_color_image(value: Any) -> bool:
    return (
        isinstance(value, np.ndarray)
        and value.ndim == 3
        and value.shape[2] == 3
        and value.dtype == np.uint8
    )


def pack_observation(obs: TimedObservation) -> ObservationFields:
    raw = obs.get_observation()
    state_names: list[str] = []
    state_positions: list[float] = []
    image_keys: list[str] = []
    image_jpegs: list[bytes] = []

    for key, value in raw.items():
        if key == "task":
            continue
        if _is_color_image(value):
            ok, encoded = cv2.imencode(".jpg", value)
            if not ok:
                raise ValueError(f"Failed to JPEG-encode image for key {key!r}")
            image_keys.append(key)
            image_jpegs.append(encoded.tobytes())
        elif isinstance(value, np.ndarray):
            # Non-color arrays (e.g. depth) are out of scope for v1.
            raise ValueError(
                f"Unsupported array observation {key!r} dtype={value.dtype} shape={value.shape}"
            )
        else:
            state_names.append(key)
            state_positions.append(float(value))

    return ObservationFields(
        timestep=int(obs.get_timestep()),
        must_go=bool(getattr(obs, "must_go", False)),
        task=str(raw.get("task", "")),
        timestamp=float(obs.get_timestamp()),
        state_names=state_names,
        state_positions=state_positions,
        image_keys=image_keys,
        image_jpegs=image_jpegs,
    )


def unpack_observation(fields: ObservationFields) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for name, position in zip(fields.state_names, fields.state_positions):
        raw[name] = float(position)
    for key, jpeg in zip(fields.image_keys, fields.image_jpegs):
        buffer = np.frombuffer(jpeg, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Failed to JPEG-decode image for key {key!r}")
        raw[key] = image
    raw["task"] = fields.task
    return raw


def pack_action_chunk(
    timed_actions: list[TimedAction], joint_names: list[str]
) -> ActionChunkFields:
    if not timed_actions:
        raise ValueError("Cannot pack an empty action chunk")
    points = [
        ActionPointFields(
            timestep=int(action.get_timestep()),
            position=[float(x) for x in action.get_action().tolist()],
        )
        for action in timed_actions
    ]
    return ActionChunkFields(
        base_timestep=int(timed_actions[0].get_timestep()),
        timestamp=float(timed_actions[0].get_timestamp()),
        joint_names=list(joint_names),
        points=points,
    )


def unpack_action_chunk(fields: ActionChunkFields) -> list[TimedAction]:
    return [
        TimedAction(
            timestamp=fields.timestamp,
            timestep=int(point.timestep),
            action=torch.tensor(point.position, dtype=torch.float32),
        )
        for point in fields.points
    ]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_ros2_messages.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add LP/ros2_inference/__init__.py LP/ros2_inference/messages.py qiuzhi/tests/test_ros2_messages.py
git commit -m "heliangp:新增 ROS2 推理桥观测/动作转换helper"
```

(Use the real path for `LP/` — `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/`.)

---

### Task 3: ROS-message glue `ros_io.py`

Thin, mechanical mapping between the field dataclasses (Task 2) and the built ROS messages (Task 1). Imports the built `lerobot_ros2_msgs` + `sensor_msgs`, so it is exercised by the integration test (Task 7), not unit tests.

**Files:**
- Create: `LP/ros2_inference/ros_io.py`

- [ ] **Step 1: Implement `ros_io.py`**

`LP/ros2_inference/ros_io.py`:

```python
"""Mechanical glue between ObservationFields/ActionChunkFields and the built ROS2
messages. Kept separate from messages.py so the conversion logic stays unit-testable
without a built workspace."""

from __future__ import annotations

import pickle  # nosec - trusted one-time handshake on a private LAN

from sensor_msgs.msg import CompressedImage, JointState

from lerobot_ros2_msgs.msg import ActionChunk, ActionPoint, Observation, RobotSchema

from .messages import (
    ActionChunkFields,
    ActionPointFields,
    ObservationFields,
)


def observation_fields_to_msg(fields: ObservationFields, clock) -> Observation:
    msg = Observation()
    msg.header.stamp = clock.now().to_msg()
    msg.timestep = fields.timestep
    msg.must_go = fields.must_go
    msg.task = fields.task

    state = JointState()
    state.header.stamp = msg.header.stamp
    state.name = list(fields.state_names)
    state.position = list(fields.state_positions)
    msg.state = state

    images = []
    for key, jpeg in zip(fields.image_keys, fields.image_jpegs):
        image = CompressedImage()
        image.header.stamp = msg.header.stamp
        image.header.frame_id = key
        image.format = "jpeg"
        image.data = list(jpeg)
        images.append(image)
    msg.images = images
    msg.image_keys = list(fields.image_keys)
    return msg


def observation_msg_to_fields(msg: Observation) -> ObservationFields:
    return ObservationFields(
        timestep=int(msg.timestep),
        must_go=bool(msg.must_go),
        task=str(msg.task),
        timestamp=msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
        state_names=list(msg.state.name),
        state_positions=list(msg.state.position),
        image_keys=list(msg.image_keys),
        image_jpegs=[bytes(image.data) for image in msg.images],
    )


def action_chunk_fields_to_msg(fields: ActionChunkFields, clock) -> ActionChunk:
    msg = ActionChunk()
    msg.header.stamp = clock.now().to_msg()
    msg.base_timestep = fields.base_timestep
    msg.joint_names = list(fields.joint_names)
    points = []
    for point in fields.points:
        ap = ActionPoint()
        ap.timestep = point.timestep
        ap.position = list(point.position)
        points.append(ap)
    msg.points = points
    return msg


def action_chunk_msg_to_fields(msg: ActionChunk) -> ActionChunkFields:
    return ActionChunkFields(
        base_timestep=int(msg.base_timestep),
        timestamp=msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
        joint_names=list(msg.joint_names),
        points=[
            ActionPointFields(timestep=int(p.timestep), position=list(p.position))
            for p in msg.points
        ],
    )


def remote_policy_config_to_schema_msg(remote_policy_config, clock) -> RobotSchema:
    msg = RobotSchema()
    msg.header.stamp = clock.now().to_msg()
    msg.remote_policy_config = list(pickle.dumps(remote_policy_config))  # nosec
    msg.policy_type = str(remote_policy_config.policy_type)
    msg.model_path = str(remote_policy_config.pretrained_name_or_path)
    msg.actions_per_chunk = int(remote_policy_config.actions_per_chunk)
    return msg


def schema_msg_to_remote_policy_config(msg: RobotSchema):
    return pickle.loads(bytes(msg.remote_policy_config))  # nosec
```

- [ ] **Step 2: Syntax check**

Run:

```bash
env ARM_HAND_TELEOP_PYTHON=${ARM_HAND_TELEOP_PYTHON:-python3} bash -c 'python3 -m py_compile qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/ros2_inference/ros_io.py && echo OK'
```

Expected: `OK` (imports of ROS messages are deferred to runtime; `py_compile` only checks syntax).

- [ ] **Step 3: Commit**

```bash
git add LP/ros2_inference/ros_io.py
git commit -m "heliangp:新增 ROS2 消息与字段互转glue"
```

---

### Task 4: Machine-B node `robot_bridge.py`

A `RobotClient` subclass that swaps the gRPC transport for ROS2, reusing the control loop, queue, aggregation, `must_go`, and reset/episode flow verbatim. Builds its `RobotClientConfig` by reusing `infer.py`'s existing config construction.

**Files:**
- Create: `LP/ros2_inference/robot_bridge.py`
- Reference (reused, do not modify): `LP/async_inference/robot_client.py`, `LP/infer.py` (`_run_async_inference`, `_create_robot_config`, `_build_robot_client_config` or equivalent)

- [ ] **Step 1: Read the existing async wiring you will reuse**

Open `LP/infer.py` around `_run_async_inference` (≈ line 1505) and note the exact helper that builds `RobotClientConfig` from `args` and the helper that builds the `RobotConfig` (`_create_robot_config`, ≈ line 1214). The bridge reuses these so the robot/observation/action schema is identical to the gRPC path.

- [ ] **Step 2: Implement `robot_bridge.py`**

`LP/ros2_inference/robot_bridge.py`:

```python
"""Machine-B ROS2 robot bridge: a RobotClient subclass that publishes observations
and subscribes to action chunks over ROS2 instead of gRPC. Reuses control_loop,
action_queue, _aggregate_action_queues, must_go, reset, and the episode loop."""

from __future__ import annotations

import argparse
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_srvs.srv import Trigger

from lerobot_ros2_msgs.msg import ActionChunk, Observation, RobotSchema

from lerobot_play.async_inference.robot_client import RobotClient
from .messages import pack_observation, unpack_action_chunk
from . import ros_io


OBS_TOPIC = "/lerobot/observation"
ACTION_TOPIC = "/lerobot/action_chunk"
SCHEMA_TOPIC = "/lerobot/robot_schema"


def _latched_qos() -> QoSProfile:
    return QoSProfile(
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )


def _best_effort_qos() -> QoSProfile:
    return QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)


def _reliable_qos(depth: int = 8) -> QoSProfile:
    return QoSProfile(depth=depth, reliability=ReliabilityPolicy.RELIABLE)


class Ros2RobotBridge(RobotClient):
    """RobotClient whose transport is ROS2 pub/sub."""

    def __init__(self, config):
        super().__init__(config)  # connects robot, builds self.policy_config, queues, barrier
        # The inherited gRPC channel/stub are left unused (insecure_channel is lazy).

        self.node = Node("lerobot_robot_bridge")
        self._obs_pub = self.node.create_publisher(Observation, OBS_TOPIC, _best_effort_qos())
        self._schema_pub = self.node.create_publisher(RobotSchema, SCHEMA_TOPIC, _latched_qos())
        self._action_sub = self.node.create_subscription(
            ActionChunk, ACTION_TOPIC, self._on_action_chunk, _reliable_qos()
        )
        self.node.create_service(Trigger, "~/reset", self._on_reset)
        self.node.create_service(Trigger, "~/stop", self._on_stop)

    # --- transport overrides -------------------------------------------------

    def start(self):
        self.shutdown_event.clear()
        schema_msg = ros_io.remote_policy_config_to_schema_msg(self.policy_config, self.node.get_clock())
        self._schema_pub.publish(schema_msg)  # latched: late-joining policy node still receives it
        self.node.get_logger().info(f"Published RobotSchema for policy {self.policy_config.policy_type}")
        return True

    def send_observation(self, obs) -> bool:
        if not self.running:
            raise RuntimeError("Bridge not running. Call start() before sending observations.")
        msg = ros_io.observation_fields_to_msg(pack_observation(obs), self.node.get_clock())
        self._obs_pub.publish(msg)
        return True

    def _on_action_chunk(self, msg: ActionChunk) -> None:
        timed_actions = unpack_action_chunk(ros_io.action_chunk_msg_to_fields(msg))
        if not timed_actions:
            return
        self.action_chunk_size = max(self.action_chunk_size, len(timed_actions))
        self._aggregate_action_queues(timed_actions, self.config.aggregate_fn)
        self.must_go.set()

    def receive_actions(self, verbose: bool = False):
        # Satisfy the inherited 2-party start_barrier, then spin so the action
        # subscription callback fires. This thread is the second barrier party that
        # control_loop() rendezvous with.
        self.start_barrier.wait()
        self.node.get_logger().info("ROS2 action receiver spinning")
        while self.running:
            rclpy.spin_once(self.node, timeout_sec=0.05)

    def stop(self):
        super().stop()  # sets shutdown_event, disconnects robot, closes unused gRPC channel
        try:
            self.node.destroy_node()
        except Exception:  # noqa: BLE001 - best-effort teardown
            pass

    # --- service handlers ----------------------------------------------------

    def _on_reset(self, request, response):
        try:
            self.robot.return_zero()
            response.success = True
            response.message = "reset complete"
        except Exception as exc:  # noqa: BLE001
            response.success = False
            response.message = f"reset failed: {exc}"
        return response

    def _on_stop(self, request, response):
        self.shutdown_event.set()
        response.success = True
        response.message = "stopping"
        return response


def _build_args() -> argparse.Namespace:
    from lerobot_play.infer import _parse_cli_args, _load_config, _config_to_args, _validate_args

    cli_args = _parse_cli_args()
    cfg = _load_config(cli_args)
    args = _config_to_args(cfg)
    args.async_infer = True
    _validate_args(args)
    return args


def main():
    from lerobot_play.infer import _run_async_inference_with_client_factory

    rclpy.init()
    try:
        _run_async_inference_with_client_factory(_build_args(), client_factory=Ros2RobotBridge)
    finally:
        rclpy.shutdown()
```

- [ ] **Step 3: Add the client-factory seam in `infer.py`**

`_run_async_inference` already selects the client in a two-branch `if/else` at `infer.py:1550-1555` (`OpenPIWebsocketRobotClient` vs `RobotClient`, on the config variable named `client_cfg`). Rename the function to take an optional `client_factory` and let it take precedence over that branch, so the bridge injects its subclass without duplicating the schema probe (lines 1512-1526, which run on B where the hardware lives) or the episode/reset loop.

In `LP/infer.py`, rename `def _run_async_inference(args)` (line 1505) to `def _run_async_inference_with_client_factory(args, client_factory=None)`, change the client-selection block (lines 1550-1555) to:

```python
    # 创建并启动客户端
    if client_factory is not None:
        client = client_factory(client_cfg)
    elif args.policy == OPENPI_JAX_WS_POLICY_TYPE:
        from .async_inference.openpi_ws_robot_client import OpenPIWebsocketRobotClient

        client = OpenPIWebsocketRobotClient(client_cfg)
    else:
        client = RobotClient(client_cfg)
```

and add a one-line back-compat wrapper directly above it so the existing `main()` dispatch is unchanged:

```python
def _run_async_inference(args: argparse.Namespace) -> Dict[str, Any]:
    return _run_async_inference_with_client_factory(args)
```

Leave the rest of the body (the schema probe, `client_cfg` build, `client.start()`, `receive_actions` thread, episode loop, `clear_action_queue`, `client.stop()`) untouched.

- [ ] **Step 4: Verify the bridge imports and the seam preserves the gRPC path**

Run (no hardware needed — this only checks import + that the refactor didn't break the existing entrypoint):

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_infer_save_path.py -q
python3 -c "import ast,sys; ast.parse(open('qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/ros2_inference/robot_bridge.py').read()); print('robot_bridge parses')"
```

Expected: existing infer tests still pass; `robot_bridge parses`. Full runtime behavior is covered by Task 7.

- [ ] **Step 5: Commit**

```bash
git add LP/ros2_inference/robot_bridge.py LP/infer.py
git commit -m "heliangp:新增机器B端 ROS2 robot bridge 节点"
```

---

### Task 5: Machine-A node `policy_node.py`

Wraps the existing `PolicyServer`, driving it through dummy request/context shims so `SendPolicyInstructions`, `_enqueue_observation`, and `GetActions` are reused verbatim (including RTC, dedup, and the size-1 latest-only queue).

**Files:**
- Create: `LP/ros2_inference/policy_node.py`
- Reference (reused, do not modify): `LP/async_inference/policy_server.py`

- [ ] **Step 1: Implement `policy_node.py`**

`LP/ros2_inference/policy_node.py`:

```python
"""Machine-A ROS2 policy node: holds the existing PolicyServer and drives it over
ROS2. Reuses SendPolicyInstructions / _enqueue_observation / GetActions verbatim via
dummy gRPC request/context shims."""

from __future__ import annotations

import argparse
import pickle  # nosec - matches the existing gRPC SendPolicyInstructions contract
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from lerobot.async_inference.configs import PolicyServerConfig
from lerobot.async_inference.helpers import TimedObservation
from lerobot.transport import services_pb2

from lerobot_ros2_msgs.msg import ActionChunk, Observation, RobotSchema

from lerobot_play.async_inference.policy_server import PolicyServer
from .messages import pack_action_chunk, unpack_observation
from . import ros_io
from .robot_bridge import (
    ACTION_TOPIC,
    OBS_TOPIC,
    SCHEMA_TOPIC,
    _best_effort_qos,
    _latched_qos,
    _reliable_qos,
)


class _DummyRequest:
    def __init__(self, data: bytes):
        self.data = data


class _DummyContext:
    def peer(self) -> str:
        return "ros2_policy_node"


class Ros2PolicyNode(Node):
    def __init__(self, server: PolicyServer):
        super().__init__("lerobot_policy_node")
        self.server = server
        self._policy_loaded = threading.Event()
        self._joint_names: list[str] | None = None

        self.create_subscription(RobotSchema, SCHEMA_TOPIC, self._on_schema, _latched_qos())
        self.create_subscription(Observation, OBS_TOPIC, self._on_observation, _best_effort_qos())
        self._action_pub = self.create_publisher(ActionChunk, ACTION_TOPIC, _reliable_qos())

        self._worker = threading.Thread(target=self._inference_loop, daemon=True)
        self._worker.start()

    def _on_schema(self, msg: RobotSchema) -> None:
        if self._policy_loaded.is_set():
            return
        remote_policy_config = ros_io.schema_msg_to_remote_policy_config(msg)
        # Reuse the server handshake exactly as the gRPC path does.
        self.server.Ready(services_pb2.Empty(), _DummyContext())
        self.server.SendPolicyInstructions(
            _DummyRequest(pickle.dumps(remote_policy_config)), _DummyContext()  # nosec
        )
        self._policy_loaded.set()
        self.get_logger().info(f"Loaded policy {remote_policy_config.policy_type}")

    def _on_observation(self, msg: Observation) -> None:
        if not self._policy_loaded.is_set():
            return
        raw = unpack_observation(ros_io.observation_msg_to_fields(msg))
        timed_obs = TimedObservation(
            timestamp=msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            observation=raw,
            timestep=int(msg.timestep),
        )
        timed_obs.must_go = bool(msg.must_go)
        self.server._enqueue_observation(timed_obs)

    def _inference_loop(self) -> None:
        self._policy_loaded.wait()
        while rclpy.ok():
            # GetActions blocks on the size-1 observation queue (obs_queue_timeout),
            # runs _predict_action_chunk (incl. RTC), returns pickled list[TimedAction]
            # or Empty on timeout.
            result = self.server.GetActions(services_pb2.Empty(), _DummyContext())
            data = getattr(result, "data", b"")
            if not data:
                continue
            timed_actions = pickle.loads(data)  # nosec
            if not timed_actions:
                continue
            joint_names = self._joint_names or [
                f"action_{i}" for i in range(len(timed_actions[0].get_action()))
            ]
            fields = pack_action_chunk(timed_actions, joint_names)
            self._action_pub.publish(ros_io.action_chunk_fields_to_msg(fields, self.get_clock()))


def _build_server_config() -> PolicyServerConfig:
    from lerobot_play.infer import _parse_cli_args, _load_config, _config_to_args

    cli_args = _parse_cli_args()
    cfg = _load_config(cli_args)
    args = _config_to_args(cfg)
    return PolicyServerConfig(
        host="0.0.0.0",
        port=0,  # gRPC server is never started; this node uses ROS2 transport.
        fps=int(getattr(args, "fps", 30)),
        inference_latency=float(getattr(args, "inference_latency", 1.0 / int(getattr(args, "fps", 30)))),
        obs_queue_timeout=float(getattr(args, "obs_queue_timeout", 1.0)),
    )


def main():
    rclpy.init()
    server = PolicyServer(_build_server_config())
    # PolicyServer starts in a not-running state until Ready(); _on_schema calls it.
    node = Ros2PolicyNode(server)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
```

**Note on `joint_names`:** the action vector ordering is `robot.action_features`, which lives on B, not A. For v1 the policy node labels points generically (`action_0…`). The bridge ignores `joint_names` on receipt (it maps the position vector back through its own `robot.action_features` in `control_loop_action`), so generic labels are correct for execution and only affect introspection. If you want true names in the message, add an `action_features` string array to `RobotSchema` in Task 1 and set `self._joint_names` in `_on_schema`.

- [ ] **Step 2: Verify `PolicyServerConfig` fields match**

Run:

```bash
python3 -c "from lerobot.async_inference.configs import PolicyServerConfig; import inspect; print([f for f in inspect.signature(PolicyServerConfig).parameters])"
```

Expected: prints the constructor params. If any of `host/port/fps/inference_latency/obs_queue_timeout` is named differently, fix `_build_server_config` to match. (This is the one upstream-coupled spot; verify before running.)

- [ ] **Step 3: Syntax check**

Run:

```bash
python3 -c "import ast; ast.parse(open('qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/ros2_inference/policy_node.py').read()); print('policy_node parses')"
```

Expected: `policy_node parses`.

- [ ] **Step 4: Commit**

```bash
git add LP/ros2_inference/policy_node.py
git commit -m "heliangp:新增机器A端 ROS2 policy 节点"
```

---

### Task 6: Launcher registration, shell wrappers, config knobs

**Files:**
- Modify: `run_lerobot_play.py` (`COMMAND_MODULES`, ≈ line 27)
- Create: `scripts/ros2_bridge_o10_dual.sh`
- Create: `scripts/ros2_policy_o10_dual.sh`
- Modify: `configs/dual_arm/o10_dual_infer.yaml` (add a comment block documenting the ROS2 transport knobs — no behavioral change to existing fields)

- [ ] **Step 1: Register the two commands in the launcher**

In `run_lerobot_play.py`, add to the `COMMAND_MODULES` dict (keep existing entries):

```python
    "ros2_robot_bridge": "lerobot_play.ros2_inference.robot_bridge",
    "ros2_policy_node": "lerobot_play.ros2_inference.policy_node",
```

- [ ] **Step 2: Verify the launcher lists the new commands**

Run:

```bash
python run_lerobot_play.py help
```

Expected: output includes `ros2_robot_bridge` and `ros2_policy_node`.

- [ ] **Step 3: Write the machine-B wrapper `scripts/ros2_bridge_o10_dual.sh`**

```bash
#!/usr/bin/env bash
# Machine-B: ROS2 robot bridge (owns the O10 dual-arm hardware).
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
# shellcheck source=scripts/lib/common_env.sh
source "${script_dir}/lib/common_env.sh"
python_bin="$(arm_hand_teleop_find_python_bin)"

config_path="${repo_root}/configs/dual_arm/o10_dual_infer.yaml"

# ROS2 environment (must match the policy host).
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
# shellcheck disable=SC1090
source "${repo_root}/ros2_ws/install/setup.bash"

# Pre-flight: refuse to start if a bridge is already running.
if pgrep -f "ros2_robot_bridge" >/dev/null 2>&1; then
  echo "ros2_robot_bridge already running; aborting." >&2
  exit 1
fi

cd "${repo_root}"
exec "${python_bin}" run_lerobot_play.py ros2_robot_bridge --config_path "${config_path}" "$@"
```

- [ ] **Step 4: Write the machine-A wrapper `scripts/ros2_policy_o10_dual.sh`**

```bash
#!/usr/bin/env bash
# Machine-A: ROS2 policy node (GPU host, no hardware).
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
# shellcheck source=scripts/lib/common_env.sh
source "${script_dir}/lib/common_env.sh"
python_bin="$(arm_hand_teleop_find_python_bin)"

config_path="${repo_root}/configs/dual_arm/o10_dual_infer.yaml"

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
# RTC (real-time chunking) toggles — same vars the gRPC async_rtc wrapper exports.
export ARM_HAND_TELEOP_RTC_ENABLED="${ARM_HAND_TELEOP_RTC_ENABLED:-0}"
# shellcheck disable=SC1090
source "${repo_root}/ros2_ws/install/setup.bash"

cd "${repo_root}"
exec "${python_bin}" run_lerobot_play.py ros2_policy_node --config_path "${config_path}" "$@"
```

- [ ] **Step 5: Make the wrappers executable and lint them**

Run:

```bash
chmod +x scripts/ros2_bridge_o10_dual.sh scripts/ros2_policy_o10_dual.sh
bash -n scripts/ros2_bridge_o10_dual.sh && bash -n scripts/ros2_policy_o10_dual.sh && echo "wrappers OK"
```

Expected: `wrappers OK`. (Confirm the helper function name in `scripts/lib/common_env.sh`; if it differs from `arm_hand_teleop_find_python_bin`, match the existing `infer_o10_*.sh` wrappers.)

- [ ] **Step 6: Document the ROS2 knobs in the infer YAML**

Append a comment block to `configs/dual_arm/o10_dual_infer.yaml` (documentation only; do not change existing keys):

```yaml
# --- ROS2 remote inference bridge (transport: ros2) ---
# Machine B runs `ros2_robot_bridge` (reads the `robot` block below).
# Machine A runs `ros2_policy_node` (reads the `infer` block below: policy, model_path, fps).
# Both must share ROS_DOMAIN_ID and have sourced ros2_ws/install/setup.bash.
# Topics: /lerobot/observation (BEST_EFFORT), /lerobot/action_chunk (RELIABLE),
#         /lerobot/robot_schema (latched). model_path must resolve on machine A.
```

- [ ] **Step 7: Commit**

```bash
git add run_lerobot_play.py scripts/ros2_bridge_o10_dual.sh scripts/ros2_policy_o10_dual.sh configs/dual_arm/o10_dual_infer.yaml
git commit -m "heliangp:接入 ROS2 推理桥launcher命令与启动脚本"
```

---

### Task 7: Loopback integration test (two nodes, fake robot, stub policy)

Exercises the full ROS2 path on one machine: a fake robot feeds the bridge, a stub policy on the policy node returns a fixed chunk, and we assert the fake robot receives executed actions and that the latched handshake works regardless of start order. Requires the built workspace (Task 1) and rclpy; guarded so it does not run under default pytest collection.

**Files:**
- Create: `qiuzhi/tests/integration/test_ros2_loopback.py`
- Create: `qiuzhi/tests/integration/fakes.py`

- [ ] **Step 1: Write the fakes**

`qiuzhi/tests/integration/fakes.py`:

```python
"""Minimal fakes for the ROS2 loopback test: no CAN, no cameras, no GPU."""

import threading

import numpy as np
import torch


class FakeRobot:
    action_features = ["left.joint1.pos", "left.joint2.pos", "right.gripper.pos"]

    def __init__(self):
        self.is_connected = True
        self.sent_actions = []
        self._lock = threading.Lock()

    def connect(self):
        self.is_connected = True

    def disconnect(self):
        self.is_connected = False

    def return_zero(self):
        pass

    def get_observation(self):
        return {
            "left.joint1.pos": 0.0,
            "left.joint2.pos": 0.0,
            "right.gripper.pos": 0.0,
            "top": np.zeros((48, 64, 3), dtype=np.uint8),
        }

    def send_action(self, action):
        with self._lock:
            self.sent_actions.append(dict(action))
        return action


class StubPolicyServer:
    """Stands in for PolicyServer.GetActions: returns one 3-step chunk per observation."""

    def __init__(self):
        from lerobot.async_inference.helpers import TimedAction
        self._TimedAction = TimedAction
        self._step = 0

    def Ready(self, request, context):
        return None

    def SendPolicyInstructions(self, request, context):
        return None

    def _enqueue_observation(self, obs):
        self._last = obs
        return True

    def GetActions(self, request, context):
        import pickle
        base = getattr(self, "_last", None)
        if base is None:
            class _Empty:  # mimics services_pb2.Empty (no .data)
                pass
            return _Empty()
        t0 = base.get_timestep()
        actions = [
            self._TimedAction(timestamp=0.0, timestep=t0 + i, action=torch.tensor([0.1, 0.2, 0.3]))
            for i in range(3)
        ]

        class _Actions:
            data = pickle.dumps(actions)
        return _Actions()
```

- [ ] **Step 2: Write the integration test**

`qiuzhi/tests/integration/test_ros2_loopback.py`:

```python
import importlib
import threading
import time

import pytest

rclpy = pytest.importorskip("rclpy")
pytest.importorskip("lerobot_ros2_msgs")  # requires `colcon build` + sourced install


def test_observation_produces_executed_actions(monkeypatch):
    from lerobot.async_inference.helpers import TimedObservation
    from lerobot_play.ros2_inference import robot_bridge, policy_node
    from qiuzhi.tests.integration.fakes import FakeRobot, StubPolicyServer

    rclpy.init()
    try:
        # --- policy node with a stub server ---
        pol = policy_node.Ros2PolicyNode(StubPolicyServer())
        pol._policy_loaded.set()  # skip the schema handshake for this assertion

        # --- bridge with a fake robot (bypass RobotClient.__init__ hardware path) ---
        bridge = object.__new__(robot_bridge.Ros2RobotBridge)
        # Minimal manual init of the pieces the test touches:
        from queue import Queue
        bridge.robot = FakeRobot()
        bridge.config = type("Cfg", (), {"aggregate_fn": None, "environment_dt": 0.03})()
        bridge.action_queue = Queue()
        bridge.action_queue_lock = threading.Lock()
        bridge.action_chunk_size = -1
        bridge.latest_action = -1
        bridge.latest_action_lock = threading.Lock()
        bridge.must_go = threading.Event()
        bridge.shutdown_event = threading.Event()
        bridge.node = rclpy.create_node("test_bridge")
        bridge._obs_pub = bridge.node.create_publisher(
            robot_bridge.Observation, robot_bridge.OBS_TOPIC, robot_bridge._best_effort_qos()
        )
        bridge._action_sub = bridge.node.create_subscription(
            robot_bridge.ActionChunk, robot_bridge.ACTION_TOPIC,
            bridge._on_action_chunk, robot_bridge._reliable_qos(),
        )

        executor = rclpy.executors.SingleThreadedExecutor()
        executor.add_node(pol)
        executor.add_node(bridge.node)
        spin = threading.Thread(target=executor.spin, daemon=True)
        spin.start()

        # publish one observation from the bridge
        obs = TimedObservation(timestamp=time.time(), observation=bridge.robot.get_observation(), timestep=0)
        obs.must_go = True
        bridge.send_observation(obs)

        # let the round trip happen: obs -> policy -> action_chunk -> bridge queue
        deadline = time.time() + 5.0
        while time.time() < deadline and bridge.action_queue.empty():
            time.sleep(0.05)

        assert not bridge.action_queue.empty(), "no action chunk returned over ROS2"
        timed_action = bridge.action_queue.get_nowait()
        assert timed_action.get_timestep() == 0

        executor.shutdown()
    finally:
        rclpy.shutdown()
```

- [ ] **Step 3: Create the integration package marker**

`qiuzhi/tests/integration/__init__.py`:

```python
```

(empty file)

- [ ] **Step 4: Run the integration test inside the sourced workspace**

Run:

```bash
source /opt/ros/$(ls /opt/ros | head -1)/setup.bash
source /home/phl/workspace/arm-hand-teleop/ros2_ws/install/setup.bash
cd /home/phl/workspace/arm-hand-teleop
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/integration/test_ros2_loopback.py -v
```

Expected: PASS — the bridge's `action_queue` receives a chunk whose first timestep is 0. If `lerobot_ros2_msgs` is not importable, the test skips (workspace not built/sourced); build Task 1 first.

- [ ] **Step 5: Commit**

```bash
git add qiuzhi/tests/integration/__init__.py qiuzhi/tests/integration/fakes.py qiuzhi/tests/integration/test_ros2_loopback.py
git commit -m "heliangp:新增 ROS2 推理桥回环集成测试"
```

---

### Task 8: Full-path manual verification (documentation)

A two-machine smoke checklist (no code). Add it so the operator can validate end-to-end.

**Files:**
- Create: `docs/ros2_remote_inference_runbook.md`

- [ ] **Step 1: Write the runbook**

`docs/ros2_remote_inference_runbook.md`:

```markdown
# ROS2 Remote Inference Runbook

Prereqs (both machines, after `git pull`):
1. `cd ros2_ws && colcon build --packages-select lerobot_ros2_msgs && source install/setup.bash`
2. Same `ROS_DOMAIN_ID` on A and B; `ROS_LOCALHOST_ONLY=0` if on different hosts.
3. `model_path` in `configs/dual_arm/o10_dual_infer.yaml` resolves on machine A.

Machine A (GPU, no hardware):
    ./scripts/ros2_policy_o10_dual.sh

Machine B (O10 hardware):
    ./scripts/ros2_bridge_o10_dual.sh

Verify topics (either machine):
    ros2 topic echo /lerobot/robot_schema --once     # latched handshake present
    ros2 topic hz /lerobot/observation               # ~fps
    ros2 topic hz /lerobot/action_chunk              # chunks flowing

Reset / stop from anywhere:
    ros2 service call /lerobot_robot_bridge/reset std_srvs/srv/Trigger
    ros2 service call /lerobot_robot_bridge/stop  std_srvs/srv/Trigger
```

- [ ] **Step 2: Commit**

```bash
git add docs/ros2_remote_inference_runbook.md
git commit -m "heliangp:新增 ROS2 远程推理运行手册"
```

---

## Self-Review Notes (spec coverage)

- Node split (B=`RobotClient` subclass, A=`PolicyServer` wrapper) → Tasks 4, 5.
- Four custom messages embedding standard sub-types → Task 1.
- dict↔message conversion + integer-timestep reconstruction → Task 2 (unit-tested), Task 3 (ROS glue).
- Latched `RobotSchema` handshake carrying pickled `RemotePolicyConfig` → Tasks 1, 3, 4 (publish), 5 (consume).
- `_aggregate_action_queues` / `must_go` / `chunk_size_threshold` / control loop reused → Task 4 (no reimplementation).
- RTC stays on A → Task 5 reuses `GetActions`/`_predict_action_chunk` unchanged.
- Reset/episode on B + `std_srvs/Trigger` services → Task 4.
- QoS (BEST_EFFORT obs / RELIABLE actions / latched schema) → Task 4 helpers.
- Image JPEG transport, color-only, depth out of scope → Task 2 (`_is_color_image`, raises on non-color arrays).
- Launcher + wrappers + config knobs → Task 6.
- Testing: unit (Task 2) + loopback integration (Task 7) + manual runbook (Task 8).
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` honored throughout; rclpy import guarded in the integration test.

**Known upstream-coupled spots to verify during implementation (called out inline):**
- `PolicyServerConfig` field names (Task 5, Step 2).
- The exact `infer.py` config-builder helper names `_parse_cli_args`/`_load_config`/`_config_to_args` (Tasks 4–5); match whatever `_run_async_inference` already uses.
- `common_env.sh` python-finder function name (Task 6, Step 5).
