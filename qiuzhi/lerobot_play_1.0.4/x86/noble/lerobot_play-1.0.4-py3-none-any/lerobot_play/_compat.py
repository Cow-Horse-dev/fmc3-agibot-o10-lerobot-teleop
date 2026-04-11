from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def preload_lerobot_processor():
    import lerobot.processor  # noqa: F401

    return lerobot.processor


preload_lerobot_processor()

from lerobot.teleoperators.config import TeleoperatorConfig
from lerobot.teleoperators.teleoperator import Teleoperator


__all__ = [
    "Teleoperator",
    "TeleoperatorConfig",
    "preload_lerobot_processor",
]

