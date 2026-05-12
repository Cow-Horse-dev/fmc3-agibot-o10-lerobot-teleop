#!/usr/bin/env python3
"""Manual RealSense wrist camera exposure diagnostic.

Default pytest runs do not touch hardware:

    pytest tests/test_wrist_camera_exposure_debug.py

Run against a real wrist camera explicitly:

    WRIST_CAMERA_EXPOSURE_HARDWARE=1 pytest tests/test_wrist_camera_exposure_debug.py -s
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "dual_arm" / "o10_dual_record.yaml"

if str(LEROBOT_PLAY_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_ROOT))


@dataclass(frozen=True)
class ExposureDebugSettings:
    config_path: Path = DEFAULT_CONFIG_PATH
    camera_name: str = "right_wrist"
    samples: int = 30
    warmup_frames: int = 10
    timeout_ms: int = 1000
    saturated_threshold: int = 250
    max_saturated_ratio: float = 0.02
    save_dir: Path | None = None


@dataclass(frozen=True)
class ExposureStats:
    frame_count: int
    mean_luma: float
    p95_luma: float
    max_luma: int
    saturated_ratio: float


def hardware_enabled() -> bool:
    return os.environ.get("WRIST_CAMERA_EXPOSURE_HARDWARE") == "1"


def settings_from_env(environ: dict[str, str] | None = None) -> ExposureDebugSettings:
    environ = environ or os.environ
    save_dir = environ.get("WRIST_CAMERA_SAVE_DIR")
    return ExposureDebugSettings(
        config_path=Path(environ.get("WRIST_CAMERA_CONFIG", str(DEFAULT_CONFIG_PATH))).expanduser(),
        camera_name=environ.get("WRIST_CAMERA_NAME", "right_wrist"),
        samples=int(environ.get("WRIST_CAMERA_SAMPLES", "30")),
        warmup_frames=int(environ.get("WRIST_CAMERA_WARMUP_FRAMES", "10")),
        timeout_ms=int(environ.get("WRIST_CAMERA_TIMEOUT_MS", "1000")),
        saturated_threshold=int(environ.get("WRIST_CAMERA_SATURATED_THRESHOLD", "250")),
        max_saturated_ratio=float(environ.get("WRIST_CAMERA_MAX_SATURATED_RATIO", "0.02")),
        save_dir=Path(save_dir).expanduser() if save_dir else None,
    )


def load_robot_camera_config(config_path: Path, camera_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    robot_config = config.get("robot") or {}
    cameras = robot_config.get("cameras") or {}
    controls = robot_config.get("camera_controls") or {}

    if camera_name not in cameras:
        available = ", ".join(sorted(cameras)) or "<none>"
        raise KeyError(f"Camera {camera_name!r} not found in {config_path}; available: {available}")

    camera_config = cameras[camera_name]
    camera_type = str(camera_config.get("type", "")).lower()
    if camera_type not in {"realsense", "intelrealsense"}:
        raise ValueError(f"Camera {camera_name!r} is {camera_type!r}, expected RealSense")

    return {camera_name: camera_config}, controls


def luma(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame.astype(np.float32)
    if frame.ndim != 3 or frame.shape[2] < 3:
        raise ValueError(f"Expected grayscale or HWC color frame, got shape {frame.shape}")
    rgb = frame[..., :3].astype(np.float32)
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def summarize_exposure(frames: list[np.ndarray], saturated_threshold: int) -> ExposureStats:
    if not frames:
        raise ValueError("At least one frame is required")

    luma_values = np.concatenate([luma(frame).reshape(-1) for frame in frames])
    saturated_pixels = np.count_nonzero(luma_values >= saturated_threshold)
    return ExposureStats(
        frame_count=len(frames),
        mean_luma=float(np.mean(luma_values)),
        p95_luma=float(np.percentile(luma_values, 95)),
        max_luma=int(np.max(luma_values)),
        saturated_ratio=float(saturated_pixels / luma_values.size),
    )


def print_stats(camera_name: str, controls: dict[str, Any], stats: ExposureStats) -> None:
    print(f"\nCamera: {camera_name}")
    print(f"Applied controls: {controls or '<none>'}")
    print(f"Frames: {stats.frame_count}")
    print(f"Mean luma: {stats.mean_luma:.2f}")
    print(f"P95 luma: {stats.p95_luma:.2f}")
    print(f"Max luma: {stats.max_luma}")
    print(f"Saturated ratio: {stats.saturated_ratio:.4%}")


def save_debug_frame(frame: np.ndarray, output_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = frame
    if frame.ndim == 3 and frame.shape[2] >= 3:
        image = cv2.cvtColor(frame[..., :3], cv2.COLOR_RGB2BGR)
    if not cv2.imwrite(str(output_path), image):
        raise RuntimeError(f"Failed to save {output_path}")


@pytest.mark.skipif(not hardware_enabled(), reason="set WRIST_CAMERA_EXPOSURE_HARDWARE=1 to use RealSense hardware")
def test_wrist_realsense_exposure_is_not_over_saturated() -> None:
    from lerobot.cameras.utils import make_cameras_from_configs
    from lerobot_play.utils.camera_config_parser import parse_camera_configs
    from lerobot_play.utils.realsense_controls import apply_realsense_controls

    settings = settings_from_env()
    raw_cameras, controls = load_robot_camera_config(settings.config_path, settings.camera_name)
    cameras = make_cameras_from_configs(parse_camera_configs(raw_cameras))
    camera = cameras[settings.camera_name]
    frames: list[np.ndarray] = []

    camera.connect()
    try:
        apply_realsense_controls(settings.camera_name, camera, controls)
        for _ in range(settings.warmup_frames):
            camera.async_read(timeout_ms=settings.timeout_ms)
        for _ in range(settings.samples):
            frames.append(camera.async_read(timeout_ms=settings.timeout_ms))
    finally:
        camera.disconnect()

    stats = summarize_exposure(frames, settings.saturated_threshold)
    print_stats(settings.camera_name, controls.get(settings.camera_name, {}), stats)

    if settings.save_dir is not None:
        save_debug_frame(frames[-1], settings.save_dir / f"{settings.camera_name}_exposure_debug.png")

    assert stats.saturated_ratio <= settings.max_saturated_ratio, (
        f"{settings.camera_name} appears over-exposed: {stats.saturated_ratio:.4%} pixels "
        f"are >= {settings.saturated_threshold}. Try lowering robot.camera_controls."
        f"{settings.camera_name}.exposure_us or gain in {settings.config_path}."
    )


def test_summarize_exposure_reports_saturated_ratio() -> None:
    dark = np.zeros((2, 2, 3), dtype=np.uint8)
    bright = np.full((2, 2, 3), 255, dtype=np.uint8)

    stats = summarize_exposure([dark, bright], saturated_threshold=250)

    assert stats.frame_count == 2
    assert stats.mean_luma == pytest.approx(127.5)
    assert stats.max_luma == 255
    assert stats.saturated_ratio == pytest.approx(0.5)


def test_load_robot_camera_config_rejects_non_realsense(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
robot:
  cameras:
    top:
      type: opencv
  camera_controls: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="expected RealSense"):
        load_robot_camera_config(config_path, "top")


def test_settings_from_env_accepts_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "record.yaml"
    save_dir = tmp_path / "frames"
    settings = settings_from_env(
        {
            "WRIST_CAMERA_CONFIG": str(config_path),
            "WRIST_CAMERA_NAME": "left_wrist",
            "WRIST_CAMERA_SAMPLES": "3",
            "WRIST_CAMERA_WARMUP_FRAMES": "2",
            "WRIST_CAMERA_TIMEOUT_MS": "500",
            "WRIST_CAMERA_SATURATED_THRESHOLD": "245",
            "WRIST_CAMERA_MAX_SATURATED_RATIO": "0.01",
            "WRIST_CAMERA_SAVE_DIR": str(save_dir),
        }
    )

    assert settings.config_path == config_path
    assert settings.camera_name == "left_wrist"
    assert settings.samples == 3
    assert settings.warmup_frames == 2
    assert settings.timeout_ms == 500
    assert settings.saturated_threshold == 245
    assert settings.max_saturated_ratio == pytest.approx(0.01)
    assert settings.save_dir == save_dir
