import sys
from pathlib import Path

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


def test_single_arm_tactile_feature_spec_uses_existing_names():
    from lerobot_play.utils.o10_schema import TACTILE_FULL_NAMES, tactile_raw_feature_spec, tactile_raw_key

    spec = tactile_raw_feature_spec(TACTILE_FULL_NAMES)

    assert tactile_raw_key("right") == "observation.tactile.right_raw"
    assert spec["shape"] == (130,)
    assert spec["dtype"] == "float32"
    assert spec["names"][0] == "tactile.thumb_0"
    assert spec["names"][-1] == "tactile.dorsum_24"


def test_dual_arm_action_feature_order():
    from lerobot_play.utils import agibot_o10
    from lerobot_play.utils.o10_schema import DUAL_ARM_ACTION_FEATURE_NAMES

    assert DUAL_ARM_ACTION_FEATURE_NAMES == (
        tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
    )


def test_dual_arm_gripper_and_eef_delta_feature_orders():
    from lerobot_play.utils import agibot_o10
    from lerobot_play.utils.o10_schema import (
        DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES,
        DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES,
        DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES,
    )

    assert DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES == (
        tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    )
    assert DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES == (
        tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
    )
    assert DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES == (
        tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    )


def test_dual_arm_state_feature_order_inserts_pose_after_each_side():
    from lerobot_play.utils import agibot_o10
    from lerobot_play.utils.o10_schema import DUAL_ARM_STATE_FEATURE_NAMES

    side_joint_names = (
        tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
    )
    side_dim = len(agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES) + len(agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)

    assert DUAL_ARM_STATE_FEATURE_NAMES == (
        side_joint_names[:side_dim]
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_POSE_FEATURE_NAMES)
        + side_joint_names[side_dim:]
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_POSE_FEATURE_NAMES)
    )


def test_dual_arm_tactile_specs_are_per_side_130d():
    from lerobot_play.utils.o10_schema import (
        TACTILE_FULL_NAMES,
        dual_arm_tactile_raw_feature_spec,
        dual_arm_tactile_raw_key,
    )

    left_spec = dual_arm_tactile_raw_feature_spec("left")
    right_spec = dual_arm_tactile_raw_feature_spec("right")

    assert dual_arm_tactile_raw_key("left") == "observation.tactile.left_raw"
    assert dual_arm_tactile_raw_key("right") == "observation.tactile.right_raw"
    assert left_spec["shape"] == (130,)
    assert right_spec["shape"] == (130,)
    assert left_spec["names"] == [f"left.{name}" for name in TACTILE_FULL_NAMES]
    assert right_spec["names"] == [f"right.{name}" for name in TACTILE_FULL_NAMES]


def test_dual_arm_tactile_helpers_reject_invalid_side():
    from lerobot_play.utils.o10_schema import dual_arm_tactile_raw_feature_spec, dual_arm_tactile_raw_key

    with pytest.raises(ValueError, match="side"):
        dual_arm_tactile_raw_key("lef")
    with pytest.raises(ValueError, match="side"):
        dual_arm_tactile_raw_feature_spec("LEFT")
