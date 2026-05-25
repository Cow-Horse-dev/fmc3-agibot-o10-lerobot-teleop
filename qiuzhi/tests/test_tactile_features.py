"""触觉 feature names 维度和命名一致性测试。"""
import sys
from pathlib import Path

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

from lerobot_play.utils.o10_schema import TACTILE_FINGERTIP_NAMES, TACTILE_FULL_NAMES


DUAL_ARM_TACTILE_FULL_FEATURE_NAMES = tuple(
    f"{side}.{name}"
    for side in ("left", "right")
    for name in TACTILE_FULL_NAMES
)


def test_tactile_full_names_are_built_from_fingertips_palm_and_dorsum():
    assert len(TACTILE_FINGERTIP_NAMES) == 80
    assert len(TACTILE_FULL_NAMES) == 130
    assert TACTILE_FULL_NAMES[:16] == tuple(f"tactile.thumb_{i}" for i in range(16))
    assert TACTILE_FULL_NAMES[80:105] == tuple(f"tactile.palm_{i}" for i in range(25))
    assert TACTILE_FULL_NAMES[105:130] == tuple(f"tactile.dorsum_{i}" for i in range(25))


def test_dual_arm_tactile_full_count():
    assert len(DUAL_ARM_TACTILE_FULL_FEATURE_NAMES) == 260


def test_dual_arm_tactile_full_has_both_sides():
    names = DUAL_ARM_TACTILE_FULL_FEATURE_NAMES
    left_names = [n for n in names if n.startswith("left.")]
    right_names = [n for n in names if n.startswith("right.")]
    assert len(left_names) == 130
    assert len(right_names) == 130


def test_no_duplicate_feature_names():
    assert len(set(DUAL_ARM_TACTILE_FULL_FEATURE_NAMES)) == 260
