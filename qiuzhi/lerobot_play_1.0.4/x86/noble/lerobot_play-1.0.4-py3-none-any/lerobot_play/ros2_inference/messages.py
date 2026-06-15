"""Pure conversion between LeRobot TimedObservation/TimedAction and plain field
dataclasses. No rclpy / ROS-message imports here, so this module is unit-testable
without a built ROS2 workspace or hardware. ROS-message glue lives in ros_io.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
import torch

from lerobot.async_inference.helpers import TimedAction, TimedObservation


@dataclass
class ObservationFields:
    timestep: int
    must_go: bool
    task: str
    timestamp: float
    state_names: list[str] = field(default_factory=list)
    state_positions: list[float] = field(default_factory=list)
    image_keys: list[str] = field(default_factory=list)
    image_jpegs: list[bytes] = field(default_factory=list)


@dataclass
class ActionPointFields:
    timestep: int
    position: list[float]


@dataclass
class ActionChunkFields:
    base_timestep: int
    timestamp: float
    joint_names: list[str]
    points: list[ActionPointFields]


def _is_color_image(value: Any) -> bool:
    return (
        isinstance(value, np.ndarray)
        and value.ndim == 3
        and value.shape[2] == 3
        and value.dtype == np.uint8
    )


def pack_observation(obs: TimedObservation) -> ObservationFields:
    raw = obs.get_observation()
    state_names: list[str] = []
    state_positions: list[float] = []
    image_keys: list[str] = []
    image_jpegs: list[bytes] = []

    for key, value in raw.items():
        if key == "task":
            continue
        if _is_color_image(value):
            ok, encoded = cv2.imencode(".jpg", value)
            if not ok:
                raise ValueError(f"Failed to JPEG-encode image for key {key!r}")
            image_keys.append(key)
            image_jpegs.append(encoded.tobytes())
        elif isinstance(value, np.ndarray):
            # Non-color arrays (e.g. depth) are out of scope for v1.
            raise ValueError(
                f"Unsupported array observation {key!r} dtype={value.dtype} shape={value.shape}"
            )
        else:
            state_names.append(key)
            state_positions.append(float(value))

    return ObservationFields(
        timestep=int(obs.get_timestep()),
        must_go=bool(getattr(obs, "must_go", False)),
        task=str(raw.get("task", "")),
        timestamp=float(obs.get_timestamp()),
        state_names=state_names,
        state_positions=state_positions,
        image_keys=image_keys,
        image_jpegs=image_jpegs,
    )


def unpack_observation(fields: ObservationFields) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for name, position in zip(fields.state_names, fields.state_positions):
        raw[name] = float(position)
    for key, jpeg in zip(fields.image_keys, fields.image_jpegs):
        buffer = np.frombuffer(jpeg, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Failed to JPEG-decode image for key {key!r}")
        raw[key] = image
    raw["task"] = fields.task
    return raw


def pack_action_chunk(
    timed_actions: list[TimedAction], joint_names: list[str]
) -> ActionChunkFields:
    if not timed_actions:
        raise ValueError("Cannot pack an empty action chunk")
    points = [
        ActionPointFields(
            timestep=int(action.get_timestep()),
            position=[float(x) for x in action.get_action().tolist()],
        )
        for action in timed_actions
    ]
    return ActionChunkFields(
        base_timestep=int(timed_actions[0].get_timestep()),
        timestamp=float(timed_actions[0].get_timestamp()),
        joint_names=list(joint_names),
        points=points,
    )


def unpack_action_chunk(fields: ActionChunkFields) -> list[TimedAction]:
    return [
        TimedAction(
            timestamp=fields.timestamp,
            timestep=int(point.timestep),
            action=torch.tensor(point.position, dtype=torch.float32),
        )
        for point in fields.points
    ]
