"""Machine-A ROS2 policy node: holds the existing PolicyServer and drives it over
ROS2. Reuses SendPolicyInstructions / _enqueue_observation / GetActions verbatim via
dummy gRPC request/context shims."""

from __future__ import annotations

import pickle  # nosec - matches the existing gRPC SendPolicyInstructions contract
import threading

import rclpy
from rclpy.node import Node

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
    fps = int(getattr(args, "fps", 30))
    # inference_latency / obs_queue_timeout are not surfaced by the infer YAML/args,
    # so use sensible defaults matching the async PolicyServer convention.
    return PolicyServerConfig(
        host="0.0.0.0",
        port=8080,  # inert: the gRPC server is never started, but PolicyServerConfig rejects port < 1
        fps=fps,
        inference_latency=1.0 / fps,
        obs_queue_timeout=1.0,
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
