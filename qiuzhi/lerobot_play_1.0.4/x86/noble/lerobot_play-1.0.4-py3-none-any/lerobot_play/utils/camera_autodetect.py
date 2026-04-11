from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_AUTO_CAMERA_TOKENS = {"auto", "/dev/videoN", "videoN"}


def _is_auto_camera_value(value: object) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text in _AUTO_CAMERA_TOKENS or Path(text).name == "videoN"


def _realsense_video_nodes() -> set[Path]:
    realsense_nodes: set[Path] = set()
    by_id_dir = Path("/dev/v4l/by-id")
    if not by_id_dir.exists():
        return realsense_nodes

    for symlink in by_id_dir.iterdir():
        if "realsense" not in symlink.name.lower():
            continue
        try:
            realsense_nodes.add(symlink.resolve())
        except FileNotFoundError:
            continue
    return realsense_nodes


def _parse_v4l2_devices(output: str) -> list[tuple[str, list[Path]]]:
    blocks: list[tuple[str, list[Path]]] = []
    device_name: str | None = None
    device_paths: list[Path] = []

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line:
            if device_name is not None:
                blocks.append((device_name, device_paths))
            device_name = None
            device_paths = []
            continue

        if not raw_line.startswith("\t"):
            if device_name is not None:
                blocks.append((device_name, device_paths))
            device_name = line.rstrip(":")
            device_paths = []
            continue

        candidate = line.strip()
        if candidate.startswith("/dev/video"):
            device_paths.append(Path(candidate))

    if device_name is not None:
        blocks.append((device_name, device_paths))

    return blocks


def _find_non_realsense_video_device() -> Path | None:
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        result = None

    if result is not None:
        for device_name, device_paths in _parse_v4l2_devices(result.stdout):
            if "realsense" in device_name.lower():
                continue
            if device_paths:
                return sorted(device_paths)[0]

    realsense_nodes = _realsense_video_nodes()
    for candidate in sorted(Path("/dev").glob("video*")):
        try:
            resolved = candidate.resolve()
        except FileNotFoundError:
            continue
        if resolved not in realsense_nodes:
            return candidate

    return None


def resolve_auto_opencv_cameras(cameras: dict[str, object]) -> dict[str, object]:
    cameras_to_remove: list[str] = []

    for camera_name, camera_cfg in list(cameras.items()):
        index_or_path = getattr(camera_cfg, "index_or_path", None)
        if not _is_auto_camera_value(index_or_path):
            continue

        detected_device = _find_non_realsense_video_device()
        if detected_device is None:
            logger.warning(
                "Camera '%s' is configured as auto, but no non-RealSense OpenCV "
                "camera is currently visible. Skipping this camera for now.",
                camera_name,
            )
            cameras_to_remove.append(camera_name)
            continue

        camera_cfg.index_or_path = detected_device
        logger.info("Resolved camera '%s' to %s", camera_name, detected_device)

    for camera_name in cameras_to_remove:
        cameras.pop(camera_name, None)

    return cameras
