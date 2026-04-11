from __future__ import annotations

from collections.abc import Collection
from typing import Any

import numpy as np


def _is_image_like(value: Any) -> bool:
    return isinstance(value, np.ndarray) and value.ndim in (2, 3)


def filter_display_observation(
    observation: dict[str, Any],
    camera_keys: Collection[str] | None = None,
) -> dict[str, Any]:
    allowed_camera_keys = set(camera_keys or [])
    filtered: dict[str, Any] = {}

    for key, value in observation.items():
        if _is_image_like(value):
            if key in allowed_camera_keys:
                filtered[key] = value
            continue
        filtered[key] = value

    return filtered
