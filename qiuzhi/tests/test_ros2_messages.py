import sys
from pathlib import Path

import numpy as np
import torch


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
