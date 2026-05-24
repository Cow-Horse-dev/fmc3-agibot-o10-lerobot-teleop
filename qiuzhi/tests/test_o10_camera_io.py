import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
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


class FakeColorCamera:
    def __init__(self, frame, failures=0):
        self.frame = frame
        self.failures = failures

    def async_read(self, timeout_ms):
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("read failed")
        return self.frame


class FakeDepthCamera:
    def __init__(self, color, depth, failures=0):
        self.color = color
        self.depth = depth
        self.failures = failures

    def async_read_color_and_depth(self, timeout_ms):
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("depth failed")
        return self.color, self.depth


def _config(width=4, height=3, use_depth=False):
    return SimpleNamespace(width=width, height=height, use_depth=use_depth)


def test_color_read_stores_cache():
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    frame = np.ones((3, 4, 3), dtype=np.uint8)
    reader = CameraObservationReader(
        camera_configs={"top": _config()},
        allow_read_failures=False,
        timeout_ms=123,
    )

    assert reader.read("top", FakeColorCamera(frame)) == (frame, None)
    assert reader.cache["top"][0] is frame


def test_depth_read_stores_color_and_depth():
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    color = np.ones((3, 4, 3), dtype=np.uint8)
    depth = np.ones((3, 4), dtype=np.uint16) * 7
    reader = CameraObservationReader(
        camera_configs={"wrist": _config(use_depth=True)},
        allow_read_failures=False,
        timeout_ms=200,
    )

    assert reader.read("wrist", FakeDepthCamera(color, depth)) == (color, depth)


def test_failure_reraises_when_fallback_disabled():
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    reader = CameraObservationReader(
        camera_configs={"top": _config()},
        allow_read_failures=False,
        timeout_ms=200,
    )

    with pytest.raises(RuntimeError, match="read failed"):
        reader.read("top", FakeColorCamera(np.zeros((3, 4, 3), dtype=np.uint8), failures=1))


def test_failure_reuses_cache_when_fallback_enabled(caplog):
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    cached = np.ones((3, 4, 3), dtype=np.uint8)
    reader = CameraObservationReader(
        camera_configs={"top": _config()},
        allow_read_failures=True,
        timeout_ms=200,
    )
    reader.cache["top"] = (cached, None)

    with caplog.at_level(logging.WARNING):
        assert reader.read("top", FakeColorCamera(np.zeros((3, 4, 3), dtype=np.uint8), failures=1)) == (cached, None)

    assert "reusing last frame" in caplog.text


def test_failure_without_cache_uses_zero_frame():
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    reader = CameraObservationReader(
        camera_configs={"wrist": _config(width=5, height=2, use_depth=True)},
        allow_read_failures=True,
        timeout_ms=200,
    )

    color, depth = reader.read(
        "wrist",
        FakeDepthCamera(
            np.ones((2, 5, 3), dtype=np.uint8),
            np.ones((2, 5), dtype=np.uint16),
            failures=1,
        ),
    )

    assert color.shape == (2, 5, 3)
    assert color.dtype == np.uint8
    assert np.all(color == 0)
    assert depth.shape == (2, 5)
    assert depth.dtype == np.uint16
    assert np.all(depth == 0)


def test_recovery_clears_fallback_state(caplog):
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    frame = np.ones((3, 4, 3), dtype=np.uint8)
    reader = CameraObservationReader(
        camera_configs={"top": _config()},
        allow_read_failures=True,
        timeout_ms=200,
    )
    reader.read("top", FakeColorCamera(frame, failures=1))
    assert reader.fallback_active["top"] is True

    with caplog.at_level(logging.INFO):
        reader.read("top", FakeColorCamera(frame))

    assert "Camera top recovered." in caplog.text
    assert "top" not in reader.fallback_active


def test_camera_feature_shapes_include_depth_key():
    from lerobot_play.utils.o10_camera_io import camera_feature_shapes

    assert camera_feature_shapes(
        ["top", "wrist"],
        {"top": _config(), "wrist": _config(use_depth=True)},
    ) == {
        "top": (3, 4, 3),
        "wrist": (3, 4, 3),
        "wrist_depth": (3, 4, 1),
    }
