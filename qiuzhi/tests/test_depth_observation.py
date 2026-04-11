from pathlib import Path
from threading import Lock
from types import SimpleNamespace
import sys

import numpy as np


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

from lerobot.datasets.feature_utils import hw_to_dataset_features

from lerobot_play.utils.depth_observation import (
    build_camera_feature_types,
    collect_camera_observation,
    collect_depth_observation,
    decode_depth_from_rgb_image,
    depth_observation_key,
    encode_depth_to_rgb_image,
    read_camera_frame_snapshot,
)


def test_encode_depth_to_rgb_image_round_trips_true_depth_values():
    depth_frame = np.array(
        [[0, 1, 255, 256, 1025, 4096, 65535]],
        dtype=np.uint16,
    )

    encoded_depth = encode_depth_to_rgb_image(depth_frame)
    decoded_depth = decode_depth_from_rgb_image(encoded_depth)

    assert encoded_depth.dtype == np.uint8
    assert encoded_depth.shape == (1, 7, 3)
    np.testing.assert_array_equal(decoded_depth, depth_frame)
    np.testing.assert_array_equal(
        encoded_depth[0, :, 2],
        np.array([0, 255, 255, 255, 255, 255, 255], dtype=np.uint8),
    )


def test_build_camera_feature_types_adds_depth_stream_for_depth_enabled_camera():
    camera_configs = {
        "right": SimpleNamespace(height=480, width=640, use_depth=True),
        "top": SimpleNamespace(height=480, width=640, use_depth=False),
    }

    feature_types = build_camera_feature_types(camera_configs)

    assert feature_types == {
        "right": (480, 640, 3),
        "right_depth": (480, 640, 3),
        "top": (480, 640, 3),
    }

    dataset_features = hw_to_dataset_features(
        feature_types,
        prefix="observation",
        use_video=True,
    )
    assert "observation.images.right_depth" in dataset_features
    assert dataset_features["observation.images.right_depth"]["shape"] == (480, 640, 3)


def test_collect_depth_observation_uses_latest_depth_frame_snapshot():
    camera = SimpleNamespace(
        use_depth=True,
        frame_lock=Lock(),
        latest_depth_frame=np.array([[0, 42], [255, 4096]], dtype=np.uint16),
    )

    observation = collect_depth_observation("right", camera)

    assert list(observation) == [depth_observation_key("right")]
    decoded_depth = decode_depth_from_rgb_image(observation["right_depth"])
    np.testing.assert_array_equal(decoded_depth, camera.latest_depth_frame)


def test_collect_camera_observation_keeps_rgb_and_depth_in_same_snapshot():
    camera = SimpleNamespace(
        use_depth=True,
        frame_lock=Lock(),
        latest_color_frame=np.array(
            [[[1, 2, 3], [4, 5, 6]]],
            dtype=np.uint8,
        ),
        latest_depth_frame=np.array([[7, 8]], dtype=np.uint16),
    )

    color_frame, depth_frame = read_camera_frame_snapshot(camera)
    observation = collect_camera_observation("right", camera)

    np.testing.assert_array_equal(color_frame, camera.latest_color_frame)
    np.testing.assert_array_equal(depth_frame, camera.latest_depth_frame)
    np.testing.assert_array_equal(observation["right"], camera.latest_color_frame)
    np.testing.assert_array_equal(
        decode_depth_from_rgb_image(observation["right_depth"]),
        camera.latest_depth_frame,
    )
