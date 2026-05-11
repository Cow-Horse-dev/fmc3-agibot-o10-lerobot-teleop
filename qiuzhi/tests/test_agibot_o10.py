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

from lerobot_play.utils import agibot_o10


CYLINDRICAL_POSES = {
    "left": {
        "open": [-0.03, 1.51, -0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "closed": [-0.03, 1.51, -0.7, 0.0, 0.7, 0.7, 0.0, 0.7, 0.0, 0.7],
    },
    "right": {
        "open": [0.03, -1.51, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "closed": [0.03, -1.51, 0.7, 0.0, 0.7, 0.7, 0.0, 0.7, 0.0, 0.7],
    },
}


def test_build_agibot_o10_joint_action_dict_contains_only_arm_and_hand_joints():
    action = agibot_o10.build_agibot_o10_joint_action_dict(range(16))

    assert list(action.keys()) == [
        *agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES,
        *agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES,
    ]
    assert list(action.values()) == pytest.approx([float(i) for i in range(16)])


def test_build_agibot_o10_joint_action_dict_rejects_non_joint_lengths():
    with pytest.raises(ValueError, match="must contain 16 values"):
        agibot_o10.build_agibot_o10_joint_action_dict(range(23))


def test_trigger_gesture_joint_angles_return_copies():
    open_pose = agibot_o10.get_agibot_o10_trigger_gesture_joint_angles(
        "pinch",
        "left",
        "open",
    )
    open_pose[0] = 999.0

    fresh_open_pose = agibot_o10.get_agibot_o10_trigger_gesture_joint_angles(
        "pinch",
        "left",
        "open",
    )
    assert fresh_open_pose[0] != 999.0


@pytest.mark.parametrize("handedness", ["left", "right"])
def test_cylindrical_trigger_gesture_has_perpendicular_open_and_linked_four_fingers(
    handedness,
):
    open_pose = agibot_o10.get_agibot_o10_trigger_gesture_joint_angles(
        "cylindrical",
        handedness,
        "open",
    )
    closed_pose = agibot_o10.get_agibot_o10_trigger_gesture_joint_angles(
        "cylindrical",
        handedness,
        "closed",
    )

    assert open_pose == pytest.approx(CYLINDRICAL_POSES[handedness]["open"])
    assert closed_pose == pytest.approx(CYLINDRICAL_POSES[handedness]["closed"])


def test_o10_dual_reset_pose_json_contains_cylindrical_gesture():
    reset_poses_path = WORKSPACE_ROOT / "configs" / "reset_poses" / "o10_dual_reset.json"
    data = json.loads(reset_poses_path.read_text(encoding="utf-8"))

    for handedness, states in CYLINDRICAL_POSES.items():
        for state, pose in states.items():
            assert data["gestures"]["cylindrical"][handedness][state] == pytest.approx(pose)


def test_sdk_import_error_mentions_qiuzhi_omnihand_root(monkeypatch):
    monkeypatch.delenv("QIUZHI_OMNIHAND_ROOT", raising=False)

    def fake_import_module(name: str):
        if name == "omnihand_2025":
            raise ModuleNotFoundError(name)
        raise AssertionError(f"Unexpected import attempted: {name}")

    monkeypatch.setattr(agibot_o10.importlib, "import_module", fake_import_module)

    with pytest.raises(ImportError) as exc_info:
        agibot_o10.import_omnihand_2025_module()

    assert "QIUZHI_OMNIHAND_ROOT" in str(exc_info.value)
