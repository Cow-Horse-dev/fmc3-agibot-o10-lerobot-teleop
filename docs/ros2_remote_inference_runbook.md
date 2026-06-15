# ROS2 Remote Inference Runbook

Run policy inference on machine **A** (GPU, no hardware) for an AGIBOT O10 dual-arm
robot whose hardware (arms, OmniHands, RealSense, CAN buses) is on machine **B**,
with observations/actions over ROS2.

This is additive: all existing local/gRPC inference paths are unchanged. Use ROS2
only for the split (hardware-on-B, policy-on-A) deployment.

## One-time setup (BOTH machines, after `git pull`)

1. Build the message interface package and source it once per machine:

   ```bash
   cd ros2_ws
   colcon build --packages-select lerobot_ros2_msgs
   source install/setup.bash
   ```

   (The launch wrappers also source it, but the package must be built once per machine.)

2. Use the SAME `ROS_DOMAIN_ID` on A and B; set `ROS_LOCALHOST_ONLY=0` if they are on
   different hosts. (The wrappers default `ROS_DOMAIN_ID=0`, `ROS_LOCALHOST_ONLY=0`.)

3. `model_path` (in `configs/dual_arm/o10_dual_infer.yaml` or the
   `ARM_HAND_TELEOP_PI05_MODEL_PATH` env var) must resolve on **both** machines:
   - machine B validates/probes the policy config (reads `config.json`),
   - machine A loads the full checkpoint.
   Use the same absolute path on both (sync the checkpoint, or use a shared mount).

## Run

Start order does not matter — the `RobotSchema` handshake is latched (TRANSIENT_LOCAL).

- Machine A (GPU):

  ```bash
  ./scripts/o10/dual_arm/ros2_policy_o10_dual.sh
  ```

- Machine B (O10 hardware):

  ```bash
  ./scripts/o10/dual_arm/ros2_bridge_o10_dual.sh
  ```

## Verify (either machine, in a ROS2-sourced shell)

```bash
ros2 topic echo /lerobot/robot_schema --once   # latched handshake present
ros2 topic hz /lerobot/observation             # ~fps
ros2 topic hz /lerobot/action_chunk            # chunks flowing
ros2 node list                                 # /lerobot_robot_bridge, /lerobot_policy_node
```

## Reset / stop on demand (either machine)

```bash
ros2 service call /lerobot_robot_bridge/reset std_srvs/srv/Trigger "{}"
ros2 service call /lerobot_robot_bridge/stop  std_srvs/srv/Trigger "{}"
```

By default machine B runs the existing episode loop (`num_episodes` with a reset
between episodes), exactly like the gRPC async path; the services are for an operator
to trigger reset/stop on demand. A reset quiesces the control loop (it cannot run
concurrently with `send_action`/`get_observation`).

## Topics and QoS

| Topic | Type | QoS |
| --- | --- | --- |
| `/lerobot/observation` | `lerobot_ros2_msgs/Observation` | BEST_EFFORT, depth 1 (latest-only) |
| `/lerobot/action_chunk` | `lerobot_ros2_msgs/ActionChunk` | RELIABLE, depth 8 |
| `/lerobot/robot_schema` | `lerobot_ros2_msgs/RobotSchema` | RELIABLE + TRANSIENT_LOCAL (latched) |

## Knobs (env vars, defaulted in the wrappers)

- `ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY`
- `ARM_HAND_TELEOP_ASYNC_FPS` (default 15)
- `ARM_HAND_TELEOP_POLICY` (default `pi05`), `ARM_HAND_TELEOP_PI05_MODEL_PATH`
- `ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK` (50), `ARM_HAND_TELEOP_ASYNC_CHUNK_SIZE_THRESHOLD` (0.8)
- RTC (machine A): `ARM_HAND_TELEOP_RTC_ENABLED` (1), `_EXECUTION_HORIZON`,
  `_MAX_GUIDANCE_WEIGHT`, `_PREFIX_ATTENTION_SCHEDULE`

## Remote launch (optional)

ROS2 does not start processes on the other machine for you — DDS only carries data once
both nodes are up. To start B's bridge from A, SSH in and run the wrapper:

```bash
ssh <user>@<B-host> 'cd ~/workspace/arm-hand-teleop && ./scripts/o10/dual_arm/ros2_bridge_o10_dual.sh'
```
