from __future__ import annotations

from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_EEF_DELTA_FEATURE_NAMES,
    AGIBOT_O10_GRIPPER_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AGIBOT_O10_POSE_FEATURE_NAMES,
)


NUM_O10_ARM_JOINTS = len(AGIBOT_O10_ARM_FEATURE_NAMES)
NUM_O10_HAND_JOINTS = len(AGIBOT_O10_HAND_FEATURE_NAMES)
SIDE_ACTION_DIM = NUM_O10_ARM_JOINTS + NUM_O10_HAND_JOINTS

DUAL_ARM_ACTION_FEATURE_NAMES = (
    tuple(f"left.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES)
    + tuple(f"left.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES)
)

DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES = (
    tuple(f"left.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    + tuple(f"left.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES)
)

DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES = (
    tuple(f"left.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES)
    + tuple(f"left.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES)
)

DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES = (
    tuple(f"left.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    + tuple(f"left.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES)
)

DUAL_ARM_EEF_ABSOLUTE_ACTION_FEATURE_NAMES = (
    tuple(f"left.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES)
    + tuple(f"left.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES)
)

DUAL_ARM_EEF_ABSOLUTE_GRIPPER_ACTION_FEATURE_NAMES = (
    tuple(f"left.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES)
    + tuple(f"left.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES)
)

DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES = DUAL_ARM_ACTION_FEATURE_NAMES
DUAL_ARM_GRIPPER_STATE_FEATURE_NAMES = DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES
DUAL_ARM_STATE_FEATURE_NAMES = (
    DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES[:SIDE_ACTION_DIM]
    + tuple(f"left.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES)
    + DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES[SIDE_ACTION_DIM:]
    + tuple(f"right.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES)
)

TACTILE_FINGERTIP_NAMES = tuple(
    f"tactile.{finger}_{index}"
    for finger in ("thumb", "index", "middle", "ring", "little")
    for index in range(16)
)
TACTILE_FULL_NAMES = (
    TACTILE_FINGERTIP_NAMES
    + tuple(f"tactile.palm_{index}" for index in range(25))
    + tuple(f"tactile.dorsum_{index}" for index in range(25))
)

LEFT_TACTILE_RAW_KEY = "observation.tactile.left_raw"
RIGHT_TACTILE_RAW_KEY = "observation.tactile.right_raw"


def tactile_raw_key(handedness: str) -> str:
    return f"observation.tactile.{handedness}_raw"


def tactile_raw_feature_spec(names: tuple[str, ...]) -> dict[str, object]:
    return {
        "dtype": "float32",
        "shape": (len(names),),
        "names": list(names),
    }


def _validate_dual_arm_side(side: str) -> str:
    if side not in ("left", "right"):
        raise ValueError("side must be 'left' or 'right'")
    return side


def dual_arm_tactile_raw_key(side: str) -> str:
    side = _validate_dual_arm_side(side)
    return LEFT_TACTILE_RAW_KEY if side == "left" else RIGHT_TACTILE_RAW_KEY


def dual_arm_tactile_raw_feature_spec(side: str) -> dict[str, object]:
    side = _validate_dual_arm_side(side)
    return tactile_raw_feature_spec(
        tuple(f"{side}.{name}" for name in TACTILE_FULL_NAMES)
    )
