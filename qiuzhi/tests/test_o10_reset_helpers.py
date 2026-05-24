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


def test_load_o10_reset_targets_returns_none_without_path_or_gesture():
    from lerobot_play.utils.o10_reset import load_o10_reset_targets

    assert load_o10_reset_targets(None, "left", "pinch") == (None, None)
    assert load_o10_reset_targets("some/path.json", "left", None) == (None, None)


def test_load_o10_reset_targets_loads_real_json():
    from lerobot_play.utils.o10_reset import load_o10_reset_targets

    reset_poses_path = REPO_ROOT.parent / "configs" / "reset_poses" / "o10_dual_reset.json"
    arm, hand = load_o10_reset_targets(reset_poses_path, "left", "pinch")

    assert len(arm) == 6
    assert len(hand) == 10


def test_normalize_joint_values_uses_store():
    from lerobot_play.utils.o10_reset import normalize_joint_values

    class Store:
        def normalize(self, values):
            return [float(value) + 1.0 for value in values]

    assert normalize_joint_values(Store(), [1, 2, 3]) == [2.0, 3.0, 4.0]


def test_load_o10_reset_targets_propagates_json_errors(tmp_path):
    from lerobot_play.utils.o10_reset import load_o10_reset_targets

    reset_path = tmp_path / "bad.json"
    reset_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="arm"):
        load_o10_reset_targets(reset_path, "left", "pinch")
