# ROS2 Remote Inference Bridge Design

## Goal

Run policy inference on a GPU host (machine **A**) that drives an AGIBOT O10
dual-arm robot whose hardware (arms, OmniHands, RealSense cameras, CAN buses) is
physically attached to a separate host (machine **B**), with observations and
actions flowing over **ROS2** instead of the existing gRPC async transport.

Machine B already runs a ROS2 ecosystem; exposing the loop over ROS2 lets B reuse
ROS2 tooling (rosbag record/replay, other ROS2 nodes). Both machines run this same
git repository (B pulls and runs).

## Context: reuse the existing async architecture

The vendored `lerobot_play` already splits inference into a robot-side half and a
policy-side half over gRPC, and the transport is already proven swappable:

- `RobotClient` (robot side) owns the robot, runs the fixed-fps `control_loop`,
  manages the `action_queue` + `_aggregate_action_queues` + `must_go` +
  `chunk_size_threshold` throttle, and drives `robot.send_action()`.
  (`lerobot_play/async_inference/robot_client.py`)
- `PolicyServer` (policy side) loads the policy, runs `_predict_action_chunk`
  (preprocess → `predict_action_chunk` → postprocess → `_time_action_chunk`),
  and owns all RTC (real-time chunking) state.
  (`lerobot_play/async_inference/policy_server.py`)
- `OpenPIWebsocketRobotClient` subclasses `RobotClient` and overrides only the
  transport methods (`send_observation`, `receive_actions`, `_time_action_chunk`)
  to swap gRPC for websockets, reusing the control loop, queue, aggregation, and
  `must_go` coordination verbatim.
  (`lerobot_play/async_inference/openpi_ws_robot_client.py`)

This design follows the `OpenPIWebsocketRobotClient` pattern: swap the transport to
ROS2, reuse everything else.

## Architecture

Two new nodes, dispatched through the existing launcher
(`run_lerobot_play.py` → `COMMAND_MODULES`):

### Machine B — `ros2_robot_bridge`

A `RobotClient` subclass that replaces the gRPC transport with ROS2 pub/sub.

- **Reused verbatim:** robot connect/disconnect, `control_loop`, `control_loop_action`
  (tensor→action-dict conversion via `robot.action_features`), `action_queue` +
  `action_queue_lock`, `_aggregate_action_queues`, `latest_action` watermark,
  `_ready_to_send_observation` / `chunk_size_threshold` gating, `must_go`
  coordination, FPS pacing, `clear_action_queue`, the per-episode reset flow
  (`robot.return_zero()` / `reset_zero`), and the `for episode_idx in range(num_episodes)`
  episode loop.
- **Overridden for ROS2:**
  - `send_observation(TimedObservation)` → publish one `Observation` message.
  - `receive_actions()` daemon → a ROS2 subscription callback on the action topic
    that deserializes an `ActionChunk`, calls `_aggregate_action_queues`, sets
    `must_go`. (No polling; callback-driven.)
  - `start()`/`stop()` → publish the latched `RobotSchema` handshake on start;
    destroy node + disconnect robot on stop.
- **Owns:** the robot, the episode loop, and reset. Episode/reset orchestration
  stays on B exactly as in the current client-side design.

### Machine A — `ros2_policy_node`

A ROS2 node wrapping `PolicyServer`'s prediction logic. No hardware, no CAN, no
cameras.

- **Reused verbatim:** `_load_policy` / policy loading + device placement,
  `make_pre_post_processors` and pre/post-processor overrides, `_predict_action_chunk`
  / `_get_action_chunk` / `_time_action_chunk`, observation dedup (`_obs_sanity_checks`,
  the size-1 latest-only queue semantics), RTC state machine
  (`_rtc_previous_action_chunk`, `_rtc_previous_timestep`, `_apply_rtc_env_config`)
  and task switching.
- **Overridden for ROS2:**
  - The latched `RobotSchema` subscription replaces `SendPolicyInstructions`:
    on receipt, load the policy and build processors.
  - The `Observation` subscription replaces `SendObservations`: rebuild the raw
    observation dict, enqueue (latest-only).
  - Publishing an `ActionChunk` replaces the `GetActions` reply: after inference,
    publish the timed action chunk.
- **Owns:** all RTC state (as today, RTC lives entirely on the policy side; nothing
  is sent back to B).

## Message contract — `lerobot_ros2_msgs` (minimal custom interface package)

A pure-standard-message design cannot cleanly carry the integer `timestep`
watermark and `must_go` flag that `_aggregate_action_queues` and RTC depend on, and
splitting cameras across separate topics risks temporal misalignment
(`ThreadPoolExecutor.as_completed` does not guarantee same-instant frames). A tiny
custom package solves both. Cost: a one-time `colcon build` per machine (the package
is in the repo). The messages embed standard sub-types, so `rosbag` still records and
replays full-fidelity sessions.

Package location: `ros2_ws/src/lerobot_ros2_msgs/`. Four message files
(`Observation`, `ActionChunk`, `ActionPoint`, `RobotSchema` — the last defined in
the Handshake section below):

```
# Observation.msg  — one atomic, temporally-consistent observation frame
std_msgs/Header           header        # stamp = capture wall-clock; for ROS tooling
int64                     timestep      # action watermark = max(latest_action, 0)
bool                      must_go
string                    task
sensor_msgs/JointState    state         # name[] + position[] for ALL scalar features
sensor_msgs/CompressedImage[] images    # one JPEG entry per camera
string[]                  image_keys    # camera keys aligned with images[]

# ActionChunk.msg  — maps 1:1 to list[TimedAction]
std_msgs/Header   header
int64             base_timestep         # the obs timestep this chunk was computed from
string[]          joint_names           # = robot.action_features order
ActionPoint[]     points

# ActionPoint.msg
int64       timestep
float64[]   position                    # action vector in joint_names order
```

### Field mapping

- **Observation state.** `robot.get_observation()` returns a flat dict of named
  scalar features plus camera ndarrays plus `task`. Scalars (e.g.
  `left.joint1.pos … left.joint6.pos`, hand `left.thumb_cm_roll.pos …
  left.pinky_mp_pitch.pos` or `left.gripper.pos`, optional eef `left.pose.x/y/z` +
  `left.quaternion.qx/qy/qz/qw`, ×2 sides) go into `state.name[]` / `state.position[]`.
  A rebuilds the identical dict by zipping `name`/`position`, decoding each
  `images[i]` into `image_keys[i]`, and re-attaching `task`, then feeds it to the
  unchanged `_predict_action_chunk` path.
- **Action chunk.** A's `_time_action_chunk` produces `list[TimedAction]`; each
  becomes an `ActionPoint{timestep, position=action_vector}` with
  `joint_names = robot.action_features`. B rebuilds `TimedAction(timestep, tensor)`,
  runs `_aggregate_action_queues`, and `control_loop_action` converts tensor→dict
  using the existing `robot.action_features` mapping. `base_timestep` is redundant
  with per-point `timestep` but kept for validation/logging.
- **Images.** Color frames (uint8 HWC) are JPEG-encoded into `CompressedImage`
  (`format: "jpeg"`). Depth is out of scope (color-only policies; `vla_jepa` and the
  other VLA policies force `tactile_mode=none`).

### QoS

- `Observation` topic: `BEST_EFFORT`, depth 1 (latest-only, mirrors the server's
  size-1 obs queue; stale frames are meant to be dropped).
- `ActionChunk` topic: `RELIABLE`, small depth (do not silently drop action chunks).
- `RobotSchema` (handshake): `RELIABLE` + `TRANSIENT_LOCAL` (latched, so A can start
  after B and still receive it).
- Services: default `RELIABLE`.

## Handshake & schema (A has no hardware)

A cannot instantiate the robot to read `lerobot_features`. B (which owns the robot)
publishes a **latched `RobotSchema`** once at startup carrying the same payload the
gRPC `RemotePolicyConfig` does: `policy_type`, `pretrained_name_or_path` (`model_path`),
`lerobot_features`, `actions_per_chunk`, `rename_map`, `task`. A loads the policy and
builds processors on receipt. This keeps A generic and hardware-free.

`RobotSchema.msg` carries `lerobot_features` and `rename_map` as JSON strings (simple,
versionable) plus the scalar fields. `model_path` must resolve **on A** (the checkpoint
lives on A, the GPU host); B only names it.

```
# RobotSchema.msg  — latched startup handshake (replaces gRPC RemotePolicyConfig)
std_msgs/Header   header
string            policy_type
string            model_path            # = pretrained_name_or_path, must resolve on A
string            lerobot_features      # JSON
string            rename_map            # JSON
int64             actions_per_chunk
string            task
```

## Reset / episode / lifecycle

B owns episodes and reset (unchanged from the current client-side design). B exposes
`std_srvs/Trigger` services so either machine or an operator can drive them:

- `~/reset` — run `robot.return_zero()` to the configured reset pose.
- `~/start_episode` — begin/resume the control loop for one episode.
- `~/stop` — graceful shutdown (clear queue, disconnect robot, destroy node).

Default behavior with no external triggers = B runs the existing
`num_episodes` loop with the standard between-episode reset + settle, exactly as
`_run_async_inference` does today.

## RTC (real-time chunking)

RTC state stays entirely on A (as in `PolicyServer` today). The integer `timestep`
flowing in `Observation` and `ActionChunk` is what RTC's
`consumed_actions = max(obs_timestep - prev_timestep, 0)` and `execution_horizon`
math need — another reason the integer watermark must survive the transport.
`ARM_HAND_TELEOP_RTC_*` env vars must be set on A (the policy host); the
`ros2_policy_node` shell wrapper exports them the way
`infer_o10_dual_pi05_async_rtc.sh` does.

## Image transport / bandwidth

Wired gigabit + JPEG. ~3 cameras × 640×480 JPEG (~45 KB/frame) × 30 Hz ≈ 4 MB/s
(~32 Mbps), well within gigabit. Encoding happens on B inside `send_observation`;
decoding on A inside the observation callback.

## Code layout

- `lerobot_play/ros2_inference/__init__.py`
- `lerobot_play/ros2_inference/robot_bridge.py` — machine-B node + `main()`.
- `lerobot_play/ros2_inference/policy_node.py` — machine-A node + `main()`.
- `lerobot_play/ros2_inference/messages.py` — pure helper functions for
  dict↔message conversion and timestep reconstruction (unit-testable without ROS or
  hardware).
- `run_lerobot_play.py`: add `ros2_robot_bridge` and `ros2_policy_node` to
  `COMMAND_MODULES`.
- `scripts/.../ros2_bridge_o10_dual.sh` and `scripts/.../ros2_policy_o10_dual.sh`:
  clone the `infer_o10_*.sh` pattern — source `common_env.sh`, CAN/duplicate-process
  pre-flight (bridge only), export `ROS_DOMAIN_ID` (+ RTC env vars for policy),
  invoke the launcher.
- `ros2_ws/src/lerobot_ros2_msgs/` — the interface package (`package.xml`,
  `CMakeLists.txt`, `msg/*.msg`).
- Configs: reuse existing `configs/dual_arm/o10_dual_infer.yaml`; B reads the `robot`
  block, A reads the `infer` block. Add a small `transport: ros2` flag plus topic
  names / `ros_domain_id` / QoS knobs to the `infer` block.

## Deployment requirements

- `rclpy` available in the `arm-hand-teleop` env on both machines. Delay `rclpy.init()`
  until node creation; keep it out of import side-effects (CLAUDE.md already flags ROS
  plugin leakage — tests run with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`).
- `colcon build --packages-select lerobot_ros2_msgs` + source the install on each
  machine (one-time after pull).
- Same `ROS_DOMAIN_ID` on A and B; `ROS_LOCALHOST_ONLY=0` if on different subnets.
- `model_path` valid on A; reset-pose / camera-config paths valid on B.
- Launch order tolerant: latched `RobotSchema` + `TRANSIENT_LOCAL` means A may start
  before or after B.

## Error handling (from subsystem risk analysis)

- **Queue starvation / network jitter:** keep `chunk_size_threshold` tunable; start
  at 0.5 and monitor queue depth. Floor the control-loop sleep so a breached
  `environment_dt` budget does not busy-spin.
- **Stale/dropped actions:** `_aggregate_action_queues` already skips
  `timestep <= latest_action`; add a sequence/gap log on the `ActionChunk`
  subscription since pub/sub loses the polling-loss visibility gRPC had.
- **`_predicted_timesteps` unbounded growth:** reset it on episode boundaries.
- **Camera read failure:** keep `allow_camera_read_failures` behavior; log and skip a
  failed camera rather than aborting the loop.
- **IK failure (eef modes):** wrap `send_action` IK in try/except; fall back to the
  last valid action, log a warning, never abort the loop.
- **Clock skew:** `header.stamp` is for ROS tooling only; ordering/aggregation use the
  integer `timestep`, not wall time, so A↔B clock skew does not corrupt the loop.
- **CAN bus stuck on crash:** graceful shutdown in `finally` (disconnect robot);
  bridge shell wrapper keeps the existing duplicate-process pre-flight.

## Testing

Follow repo convention: `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/…`.

- **Unit (no ROS, no hardware):** in `lerobot_play/ros2_inference/messages.py`, test
  observation dict → `Observation` → dict round-trip (scalar names/positions, image
  keys, task, `timestep`, `must_go`), and `list[TimedAction]` → `ActionChunk` → list
  round-trip including absolute-timestep reconstruction from `base_timestep` + point
  index. Place tests under `qiuzhi/tests/test_ros2_messages.py`.
- **Integration (single machine, loopback ROS2):** run `ros2_robot_bridge` against a
  fake/mock robot and `ros2_policy_node` with a tiny policy stub on the same
  `ROS_DOMAIN_ID`; assert an observation produces an action chunk that the bridge
  executes, and that the latched handshake loads the policy regardless of start order.
  Guard rclpy usage so it does not run under the default pytest collection.

## Out of scope (v1)

- Standard `sensor_msgs` topic mirrors for live rviz (add an optional republisher
  later; `rosbag` already records the embedded images).
- Depth and tactile streaming (color-only policies; tactile forced `none`).
- ROS2 lifecycle-node state machine, multi-robot, and dynamic action/hand mode switching.
