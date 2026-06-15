"""Single-machine loopback integration test for the ROS2 remote-inference bridge.

Exercises the REAL rclpy transport end-to-end (real publishers/subscriptions on one
ROS graph, no mocked pub/sub) with a FakeRobot and a StubPolicyServer:

  bridge.send_observation()  --OBS_TOPIC-->  policy node._on_observation
      -> StubPolicyServer._enqueue_observation -> worker GetActions
      -> _action_pub  --ACTION_TOPIC-->  bridge._on_action_chunk
      -> _aggregate_action_queues -> bridge.action_queue

Skipped (not errored) when rclpy / lerobot_ros2_msgs aren't importable so the default
suite on a non-ROS machine still passes.
"""
import sys
import threading
import time
from pathlib import Path
from queue import Queue

import pytest

# Skip guards MUST be the first executable lines: a machine without the ROS workspace
# sourced cannot import these, and we want "skipped", not "error".
rclpy = pytest.importorskip("rclpy")
pytest.importorskip("lerobot_ros2_msgs")

# Standard repo preamble so lerobot_play imports (mirror other qiuzhi/tests files);
# REPO_ROOT also lets `qiuzhi.tests.integration.fakes` resolve as a namespace package
# regardless of how pytest collected this module.
REPO_ROOT = Path(__file__).resolve().parents[3]
PKG = REPO_ROOT / "qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
for path in (REPO_ROOT, PKG):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from qiuzhi.tests.integration.fakes import FakeRobot, StubPolicyServer  # noqa: E402


class _Cfg:
    """Stand-in for the bridge config: only aggregate_fn is read on this path."""

    aggregate_fn = None
    environment_dt = 0.03


def _make_bridge(robot_bridge):
    """Build a Ros2RobotBridge bypassing __init__ (which connects CAN/cameras).

    Sets exactly the attributes that send_observation / _on_action_chunk /
    _aggregate_action_queues read (verified against robot_bridge.py + robot_client.py).
    """
    bridge = object.__new__(robot_bridge.Ros2RobotBridge)
    bridge.robot = FakeRobot()
    bridge.config = _Cfg()
    bridge.action_queue = Queue()
    bridge.action_queue_lock = threading.Lock()
    bridge.action_chunk_size = -1
    bridge.latest_action = -1
    bridge.latest_action_lock = threading.Lock()
    bridge.must_go = threading.Event()
    bridge.shutdown_event = threading.Event()  # clear -> self.running is True
    bridge.node = rclpy.create_node("test_bridge")
    bridge._obs_pub = bridge.node.create_publisher(
        robot_bridge.Observation, robot_bridge.OBS_TOPIC, robot_bridge._best_effort_qos()
    )
    bridge._action_sub = bridge.node.create_subscription(
        robot_bridge.ActionChunk,
        robot_bridge.ACTION_TOPIC,
        bridge._on_action_chunk,
        robot_bridge._reliable_qos(),
    )
    return bridge


def test_observation_produces_action_chunk_over_ros2():
    from lerobot.async_inference.helpers import TimedObservation
    from lerobot_play.ros2_inference import robot_bridge, policy_node

    rclpy.init()
    try:
        stub = StubPolicyServer()
        pol = policy_node.Ros2PolicyNode(stub)
        # Skip the schema handshake for THIS assertion: mark the policy loaded so the
        # node enqueues observations and its worker publishes action chunks.
        pol._policy_loaded.set()

        bridge = _make_bridge(robot_bridge)

        executor = rclpy.executors.SingleThreadedExecutor()
        executor.add_node(pol)
        executor.add_node(bridge.node)
        spin = threading.Thread(target=executor.spin, daemon=True)
        spin.start()

        try:
            # Wait for the policy node's OBS subscription to discover the bridge's
            # OBS publisher before sending, so the best-effort message isn't dropped.
            deadline = time.time() + 5.0
            while time.time() < deadline and bridge._obs_pub.get_subscription_count() < 1:
                time.sleep(0.02)
            assert bridge._obs_pub.get_subscription_count() >= 1, (
                "policy node never subscribed to OBS_TOPIC"
            )

            obs = TimedObservation(
                timestamp=time.time(),
                observation=bridge.robot.get_observation(),
                timestep=0,
            )
            obs.must_go = True
            bridge.send_observation(obs)

            deadline = time.time() + 10.0
            while time.time() < deadline and bridge.action_queue.empty():
                time.sleep(0.05)

            assert not bridge.action_queue.empty(), "no action chunk returned over ROS2"
            timed_action = bridge.action_queue.get_nowait()
            assert timed_action.get_timestep() == 0
            assert bridge.must_go.is_set()
        finally:
            executor.shutdown()
            pol.destroy_node()
            bridge.node.destroy_node()
    finally:
        rclpy.shutdown()


def test_latched_schema_loads_policy_when_bridge_starts_first():
    """The latched RobotSchema handshake must reach a late-joining policy node.

    Publish the schema BEFORE the policy node exists; TRANSIENT_LOCAL durability must
    deliver the latched message to the late subscriber and trigger Ready/SendPolicy.
    """
    from lerobot.async_inference.helpers import RemotePolicyConfig
    from lerobot_play.ros2_inference import robot_bridge, policy_node, ros_io

    rclpy.init()
    try:
        # --- bridge side: publish a latched schema, no policy node listening yet ---
        node = rclpy.create_node("test_schema_bridge")
        schema_pub = node.create_publisher(
            robot_bridge.RobotSchema, robot_bridge.SCHEMA_TOPIC, robot_bridge._latched_qos()
        )

        # Real (top-level, picklable) config so the schema round-trips through
        # pickle exactly as the production handshake does.
        remote_policy_config = RemotePolicyConfig(
            policy_type="act",
            pretrained_name_or_path="/tmp/fake-model",
            lerobot_features={},
            actions_per_chunk=3,
        )
        schema_msg = ros_io.remote_policy_config_to_schema_msg(
            remote_policy_config, node.get_clock()
        )
        schema_pub.publish(schema_msg)

        # Spin the publisher node a moment so the latched sample is retained by DDS,
        # then leave it on the executor as a live publisher for the late subscriber.
        executor = rclpy.executors.SingleThreadedExecutor()
        executor.add_node(node)
        for _ in range(10):
            executor.spin_once(timeout_sec=0.05)

        # --- policy side: start AFTER the schema was published ---
        stub = StubPolicyServer()
        pol = policy_node.Ros2PolicyNode(stub)
        executor.add_node(pol)

        # Spin both nodes on one background-threaded executor. Spinning the executor
        # (vs. hand-pumping spin_once) lets the wait-set service the latched
        # TRANSIENT_LOCAL delivery to the late subscriber promptly under Fast-DDS.
        spin = threading.Thread(target=executor.spin, daemon=True)
        spin.start()

        deadline = time.time() + 15.0
        while time.time() < deadline and not pol._policy_loaded.is_set():
            time.sleep(0.05)

        assert pol._policy_loaded.is_set(), (
            "latched RobotSchema did not load the policy on a late-joining node"
        )

        executor.shutdown()
        pol.destroy_node()
        node.destroy_node()
    finally:
        rclpy.shutdown()
