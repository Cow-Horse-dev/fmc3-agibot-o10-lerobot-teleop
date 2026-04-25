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

from lerobot_play.utils import agibot_o10


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
