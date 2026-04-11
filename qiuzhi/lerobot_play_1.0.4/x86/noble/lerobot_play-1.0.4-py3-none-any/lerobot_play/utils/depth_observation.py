from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np


DEPTH_OBSERVATION_SUFFIX = "_depth"


def depth_observation_key(camera_name: str) -> str:
    return f"{camera_name}{DEPTH_OBSERVATION_SUFFIX}"


def has_depth_stream(camera_or_config: Any) -> bool:
    return bool(getattr(camera_or_config, "use_depth", False))


def build_camera_feature_types(
    camera_configs: Mapping[str, Any],
) -> dict[str, tuple[int, int, int]]:
    feature_types: dict[str, tuple[int, int, int]] = {}
    camera_names = set(camera_configs)

    for camera_name, camera_config in camera_configs.items():
        shape = (int(camera_config.height), int(camera_config.width), 3)
        feature_types[camera_name] = shape

        if not has_depth_stream(camera_config):
            continue

        depth_key = depth_observation_key(camera_name)
        if depth_key in camera_names:
            raise ValueError(
                f"Depth observation key '{depth_key}' conflicts with an existing camera name."
            )
        feature_types[depth_key] = shape

    return feature_types


def encode_depth_to_rgb_image(depth_frame: np.ndarray) -> np.ndarray:
    depth_array = np.asarray(depth_frame)
    if depth_array.ndim != 2:
        raise ValueError(
            f"Depth frame must be a 2D array, got shape {depth_array.shape}"
        )

    clipped_depth = np.clip(depth_array, 0, np.iinfo(np.uint16).max).astype(
        np.uint16, copy=False
    )
    low_byte = (clipped_depth & 0xFF).astype(np.uint8)
    high_byte = ((clipped_depth >> 8) & 0xFF).astype(np.uint8)
    valid_mask = (clipped_depth > 0).astype(np.uint8) * 255
    return np.stack((low_byte, high_byte, valid_mask), axis=-1)


def decode_depth_from_rgb_image(encoded_depth: np.ndarray) -> np.ndarray:
    encoded_array = np.asarray(encoded_depth)
    if encoded_array.ndim != 3 or encoded_array.shape[-1] != 3:
        raise ValueError(
            "Encoded depth image must be an HxWx3 array."
        )

    low_byte = encoded_array[..., 0].astype(np.uint16)
    high_byte = encoded_array[..., 1].astype(np.uint16)
    decoded_depth = low_byte | (high_byte << 8)
    valid_mask = encoded_array[..., 2] > 0
    decoded_depth[~valid_mask] = 0
    return decoded_depth


def _copy_frame(frame: Any) -> np.ndarray | None:
    if frame is None:
        return None
    return np.array(frame, copy=True)


def read_camera_frame_snapshot(camera: Any) -> tuple[np.ndarray, np.ndarray | None]:
    color_frame = None
    depth_frame = None

    frame_lock = getattr(camera, "frame_lock", None)
    if frame_lock is not None:
        with frame_lock:
            color_frame = _copy_frame(
                getattr(camera, "latest_color_frame", getattr(camera, "latest_frame", None))
            )
            if has_depth_stream(camera):
                depth_frame = _copy_frame(getattr(camera, "latest_depth_frame", None))
    else:
        color_frame = _copy_frame(
            getattr(camera, "latest_color_frame", getattr(camera, "latest_frame", None))
        )
        if has_depth_stream(camera):
            depth_frame = _copy_frame(getattr(camera, "latest_depth_frame", None))

    if color_frame is None and hasattr(camera, "async_read"):
        color_frame = np.asarray(camera.async_read())

    if color_frame is None:
        raise RuntimeError("No color frame available from camera.")

    if has_depth_stream(camera) and depth_frame is None:
        depth_frame = read_latest_depth_frame(camera)

    return np.asarray(color_frame), depth_frame


def read_latest_depth_frame(camera: Any) -> np.ndarray:
    if not has_depth_stream(camera):
        raise RuntimeError("Depth stream is not enabled for this camera.")

    depth_frame = None

    frame_lock = getattr(camera, "frame_lock", None)
    if frame_lock is not None and hasattr(camera, "latest_depth_frame"):
        with frame_lock:
            latest_depth = getattr(camera, "latest_depth_frame", None)
            if latest_depth is not None:
                depth_frame = np.array(latest_depth, copy=True)
    elif hasattr(camera, "latest_depth_frame"):
        latest_depth = getattr(camera, "latest_depth_frame", None)
        if latest_depth is not None:
            depth_frame = np.array(latest_depth, copy=True)

    if depth_frame is None and hasattr(camera, "read_depth"):
        try:
            depth_frame = camera.read_depth(timeout_ms=0)
        except TypeError:
            depth_frame = camera.read_depth()

    if depth_frame is None:
        raise RuntimeError("No depth frame available from camera.")

    return np.asarray(depth_frame)


def collect_camera_observation(camera_name: str, camera: Any) -> dict[str, np.ndarray]:
    color_frame, depth_frame = read_camera_frame_snapshot(camera)
    observation = {camera_name: color_frame}

    if depth_frame is not None:
        observation[depth_observation_key(camera_name)] = encode_depth_to_rgb_image(depth_frame)

    return observation


def collect_depth_observation(camera_name: str, camera: Any) -> dict[str, np.ndarray]:
    if not has_depth_stream(camera):
        return {}

    return {
        depth_observation_key(camera_name): encode_depth_to_rgb_image(
            read_latest_depth_frame(camera)
        )
    }
