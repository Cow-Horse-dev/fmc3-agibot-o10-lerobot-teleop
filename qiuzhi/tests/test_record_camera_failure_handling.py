import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


import lerobot.datasets.utils as lerobot_dataset_utils
import lerobot.utils.utils as lerobot_utils


if not hasattr(lerobot_dataset_utils, "build_dataset_frame"):
    lerobot_dataset_utils.build_dataset_frame = lambda *args, **kwargs: {}
if not hasattr(lerobot_dataset_utils, "combine_feature_dicts"):
    lerobot_dataset_utils.combine_feature_dicts = lambda *args, **kwargs: {}
if not hasattr(lerobot_dataset_utils, "load_image_as_numpy"):
    lerobot_dataset_utils.load_image_as_numpy = lambda *args, **kwargs: None
if not hasattr(lerobot_utils, "get_safe_torch_device"):
    lerobot_utils.get_safe_torch_device = lambda *args, **kwargs: "cpu"


fake_mcap = types.ModuleType("mcap")
fake_mcap_writer = types.ModuleType("mcap.writer")
fake_mcap_reader = types.ModuleType("mcap.reader")
fake_mcap_writer.Writer = object
fake_mcap_reader.make_reader = lambda *args, **kwargs: None
sys.modules.setdefault("mcap", fake_mcap)
sys.modules.setdefault("mcap.writer", fake_mcap_writer)
sys.modules.setdefault("mcap.reader", fake_mcap_reader)

fake_lerobot_dataset = types.ModuleType("lerobot_play.utils.lerobot_dataset")
fake_lerobot_dataset.LeRobotDataset = object
sys.modules.setdefault("lerobot_play.utils.lerobot_dataset", fake_lerobot_dataset)

from lerobot_play.utils.lerobot_record import record_loop


class _IdentityProcessor:
    def __call__(self, value):
        return value

    def reset(self):
        return None


class _FailingRobot:
    cameras = {"top": object()}

    def __init__(self):
        self.observation_attempts = 0
        self.reset_calls = 0
        self.send_action_calls = 0
        self.action_features = {}
        self.observation_features = {}
        self.robot_type = "dummy"

    def get_observation(self):
        self.observation_attempts += 1
        raise TimeoutError("Timed out waiting for frame from camera top after 200 ms.")

    def reset_zero(self):
        self.reset_calls += 1

    def send_action(self, action):
        self.send_action_calls += 1
        return action


class _DummyDataset:
    fps = 30
    features = {}

    def __init__(self):
        self.clear_calls = []
        self.add_frame_calls = 0

    def clear_episode_buffer(self, restart_image_writer=False):
        self.clear_calls.append(restart_image_writer)

    def add_frame(self, frame, use_mcap=False, online_encoding=False):
        self.add_frame_calls += 1


def test_record_loop_camera_timeout_stops_and_discards_partial_episode(caplog):
    robot = _FailingRobot()
    dataset = _DummyDataset()
    events = {
        "exit_early": False,
        "reset_robot": False,
        "stop_recording": False,
        "rerecord_episode": False,
        "discard_episode": False,
        "start": True,
    }

    with caplog.at_level("ERROR"):
        record_loop(
            robot=robot,
            events=events,
            fps=30,
            teleop_action_processor=_IdentityProcessor(),
            robot_action_processor=_IdentityProcessor(),
            robot_observation_processor=_IdentityProcessor(),
            dataset=dataset,
            teleop=None,
            policy=None,
            preprocessor=None,
            postprocessor=None,
            control_time_s=1,
            single_task="test task",
            display_data=False,
            use_mcap=False,
            online_encoding=False,
            episode_index=1,
            total_episodes=1,
        )

    assert robot.observation_attempts == 1
    assert robot.send_action_calls == 0
    assert dataset.add_frame_calls == 0
    assert dataset.clear_calls == [True]
    assert events["stop_recording"] is True
    assert events["exit_early"] is True
    assert events["discard_episode"] is True
    assert "Camera read failed during recording" in caplog.text
