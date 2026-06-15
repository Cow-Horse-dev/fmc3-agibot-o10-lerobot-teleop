"""Machine-B ROS2 robot bridge: a RobotClient subclass that publishes observations
and subscribes to action chunks over ROS2 instead of gRPC. Reuses control_loop,
action_queue, _aggregate_action_queues, must_go, reset, and the episode loop."""

from __future__ import annotations

import argparse
import threading
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
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

        # Serialize ALL robot I/O (send_action/get_observation on the main control
        # loop vs. return_zero on the spin thread's reset callback) through one lock.
        self._robot_io_lock = threading.Lock()

        self.node = Node("lerobot_robot_bridge")
        self._obs_pub = self.node.create_publisher(Observation, OBS_TOPIC, _best_effort_qos())
        self._schema_pub = self.node.create_publisher(RobotSchema, SCHEMA_TOPIC, _latched_qos())
        self._action_sub = self.node.create_subscription(
            ActionChunk, ACTION_TOPIC, self._on_action_chunk, _reliable_qos()
        )
        self.node.create_service(Trigger, "~/reset", self._on_reset)
        self.node.create_service(Trigger, "~/stop", self._on_stop)

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self.node)

    # --- robot I/O serialization ---------------------------------------------

    def control_loop_action(self, verbose: bool = False):
        with self._robot_io_lock:
            return super().control_loop_action(verbose)

    def control_loop_observation(self, task: str, verbose: bool = False):
        with self._robot_io_lock:
            return super().control_loop_observation(task, verbose)

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
        # subscription + service callbacks fire. This thread is the second barrier
        # party that control_loop() rendezvous with.
        self.start_barrier.wait()
        self.node.get_logger().info("ROS2 action receiver spinning")
        while self.running:
            self._executor.spin_once(timeout_sec=0.05)

    def stop(self):
        super().stop()  # sets shutdown_event, disconnects robot, closes unused gRPC channel
        executor = getattr(self, "_executor", None)
        if executor is not None:
            try:
                executor.shutdown()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
        node = getattr(self, "node", None)
        if node is not None:
            try:
                node.destroy_node()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass

    # --- service handlers ----------------------------------------------------

    def _on_reset(self, request, response):
        try:
            with self._robot_io_lock:
                self.clear_action_queue(advance_action_watermark=True)
                self.robot.return_zero()
            response.success = True
            response.message = "reset complete"
        except Exception as exc:  # noqa: BLE001
            self.node.get_logger().error(f"reset failed: {exc}")
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
