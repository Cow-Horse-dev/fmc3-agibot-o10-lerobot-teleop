import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


def test_trigger_gesture_hand_pos_matches_builtin():
    from lerobot_play.utils import agibot_o10
    from lerobot_play.utils.o10_hand_control import trigger_gesture_hand_pos

    assert trigger_gesture_hand_pos(None, "pinch", "left", "open") == pytest.approx(
        agibot_o10.get_agibot_o10_trigger_gesture_joint_angles("pinch", "left", "open")
    )


def test_trigger_gesture_hand_pos_prefers_reset_json(tmp_path):
    from lerobot_play.utils.o10_hand_control import trigger_gesture_hand_pos

    reset_path = tmp_path / "reset.json"
    reset_path.write_text(
        json.dumps(
            {
                "gestures": {
                    "pinch": {
                        "left": {
                            "open": [float(index) for index in range(10)],
                            "closed": [float(index + 10) for index in range(10)],
                        },
                        "right": {
                            "open": [0.0] * 10,
                            "closed": [1.0] * 10,
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert trigger_gesture_hand_pos(reset_path, "pinch", "left", "open") == pytest.approx(
        [float(index) for index in range(10)]
    )


def test_gripper_value_to_hand_joints_clamps_and_interpolates():
    from lerobot_play.utils.o10_hand_control import gripper_value_to_hand_joints, trigger_gesture_hand_pos

    open_pose = trigger_gesture_hand_pos(None, "pinch", "right", "open")
    closed_pose = trigger_gesture_hand_pos(None, "pinch", "right", "closed")

    halfway = gripper_value_to_hand_joints(0.5, "pinch", "right", None)
    assert halfway == pytest.approx(
        [
            open_value + 0.5 * (closed_value - open_value)
            for open_value, closed_value in zip(open_pose, closed_pose, strict=True)
        ]
    )
    assert gripper_value_to_hand_joints(-1.0, "pinch", "right", None) == pytest.approx(open_pose)
    assert gripper_value_to_hand_joints(2.0, "pinch", "right", None) == pytest.approx(closed_pose)


def test_hand_joints_to_gripper_value_projects_onto_gesture_axis():
    from lerobot_play.utils.o10_hand_control import (
        gripper_value_to_hand_joints,
        hand_joints_to_gripper_value,
    )

    joints = gripper_value_to_hand_joints(0.25, "pinch", "left", None)

    assert hand_joints_to_gripper_value(joints, "pinch", "left", None) == pytest.approx(0.25)


def test_default_gripper_gesture_fallback_order():
    from lerobot_play.utils.o10_hand_control import default_gripper_gesture

    assert default_gripper_gesture(None, None, None) == "pinch"
    assert default_gripper_gesture(None, "tripod", "pinch") == "tripod"
    assert default_gripper_gesture("cylindrical", "tripod", "pinch") == "cylindrical"


def test_real_reset_pose_json_can_supply_trigger_gesture():
    from lerobot_play.utils.o10_hand_control import trigger_gesture_hand_pos

    reset_poses_path = WORKSPACE_ROOT / "configs" / "reset_poses" / "o10_dual_reset.json"

    assert len(trigger_gesture_hand_pos(reset_poses_path, "pinch", "left", "open")) == 10
