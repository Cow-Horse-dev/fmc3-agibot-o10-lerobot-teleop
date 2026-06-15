"""Minimal fakes for the ROS2 loopback test: no CAN, no cameras, no GPU."""
import pickle
import threading

import numpy as np
import torch

from lerobot.async_inference.helpers import TimedAction


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


class _Actions:
    """Mirror of services_pb2.Actions: carries a pickled list[TimedAction] in .data."""

    def __init__(self, data):
        self.data = data


class _Empty:
    """Mirror of services_pb2.Empty: no .data attribute -> signals "no actions"."""


class StubPolicyServer:
    """Stands in for PolicyServer: returns one 3-step chunk per enqueued observation."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last = None

    def Ready(self, request, context):
        return None

    def SendPolicyInstructions(self, request, context):
        return None

    def _enqueue_observation(self, obs):
        with self._lock:
            self._last = obs
        return True

    def GetActions(self, request, context):
        with self._lock:
            base = self._last
            self._last = None
        if base is None:
            return _Empty()
        t0 = base.get_timestep()
        actions = [
            TimedAction(
                timestamp=0.0,
                timestep=t0 + i,
                action=torch.tensor([0.1, 0.2, 0.3]),
            )
            for i in range(3)
        ]
        return _Actions(pickle.dumps(actions))
