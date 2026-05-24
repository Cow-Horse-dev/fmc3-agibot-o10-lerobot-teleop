from __future__ import annotations

from pathlib import Path
from typing import Sequence

from lerobot_play.utils.joint_target_store import load_reset_poses


def load_o10_reset_targets(
    reset_poses_path: str | Path | None,
    side: str,
    reset_gesture: str | None,
) -> tuple[list[float] | None, list[float] | None]:
    if not reset_poses_path or not reset_gesture:
        return None, None
    return load_reset_poses(reset_poses_path, side, reset_gesture)


def normalize_joint_values(store, joint_values: Sequence[float]) -> list[float]:
    return store.normalize(joint_values)
