from __future__ import annotations

from pathlib import Path
from typing import Sequence

from lerobot_play.utils.agibot_o10 import (
    agibot_o10_gripper_value_from_hand_joints,
    agibot_o10_hand_joints_from_gripper_value,
    get_agibot_o10_reset_pose_gesture_joint_angles,
    get_agibot_o10_trigger_gesture_joint_angles,
)


def default_gripper_gesture(
    gripper_gesture: str | None,
    trigger_gesture: str | None,
    reset_gesture: str | None,
) -> str:
    return gripper_gesture or trigger_gesture or reset_gesture or "pinch"


def trigger_gesture_hand_pos(
    reset_poses_path: str | Path | None,
    gesture_name: str,
    handedness: str,
    state_key: str,
) -> list[float]:
    return get_agibot_o10_reset_pose_gesture_joint_angles(
        reset_poses_path,
        gesture_name,
        handedness,
        state_key,
    ) or get_agibot_o10_trigger_gesture_joint_angles(
        gesture_name,
        handedness,
        state_key,
    )


def gripper_value_to_hand_joints(
    gripper_value: float,
    gesture_name: str,
    handedness: str,
    reset_poses_path: str | Path | None = None,
) -> list[float]:
    return agibot_o10_hand_joints_from_gripper_value(
        gripper_value,
        gesture_name,
        handedness,
        reset_poses_path=reset_poses_path,
    )


def hand_joints_to_gripper_value(
    hand_joints: Sequence[float],
    gesture_name: str,
    handedness: str,
    reset_poses_path: str | Path | None = None,
) -> float:
    return agibot_o10_gripper_value_from_hand_joints(
        hand_joints,
        gesture_name,
        handedness,
        reset_poses_path=reset_poses_path,
    )
