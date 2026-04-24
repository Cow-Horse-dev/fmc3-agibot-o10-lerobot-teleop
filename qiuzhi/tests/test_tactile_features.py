"""触觉 feature names 维度和命名一致性测试。

Strategy: exec the constant definitions from the source file directly,
bypassing the heavy import chain (airbot_hardware_py, CAN, etc.).
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_FILE = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/robots/pico_follower_dual_arm_agibot_o10"
    / "airbot_pico_follower_dual_arm_agibot_o10.py"
)


def _load_tactile_constants():
    """Extract and exec only the tactile constant block from source."""
    src = SRC_FILE.read_text()
    # The constants depend on nothing except each other.
    # Extract lines 55-97 (TACTILE_REGION_NAMES through DUAL_ARM_TACTILE_FULL_FEATURE_NAMES).
    block = []
    capture = False
    for line in src.splitlines():
        if "TACTILE_REGION_NAMES" in line and not capture:
            capture = True
        if capture:
            block.append(line)
        if capture and "# 260D" in line:
            break
    ns = {}
    exec("\n".join(block), ns)
    return ns


_NS = _load_tactile_constants()
TACTILE_REGION_NAMES = _NS["TACTILE_REGION_NAMES"]
TACTILE_FINGERTIP_NAMES = _NS["TACTILE_FINGERTIP_NAMES"]
TACTILE_FULL_NAMES = _NS["TACTILE_FULL_NAMES"]
DUAL_ARM_TACTILE_AVG_FEATURE_NAMES = _NS["DUAL_ARM_TACTILE_AVG_FEATURE_NAMES"]
DUAL_ARM_TACTILE_FINGERTIP_FEATURE_NAMES = _NS["DUAL_ARM_TACTILE_FINGERTIP_FEATURE_NAMES"]
DUAL_ARM_TACTILE_FULL_FEATURE_NAMES = _NS["DUAL_ARM_TACTILE_FULL_FEATURE_NAMES"]


def test_tactile_region_names_count():
    assert len(TACTILE_REGION_NAMES) == 7


def test_tactile_fingertip_names_count():
    assert len(TACTILE_FINGERTIP_NAMES) == 80


def test_tactile_full_names_count():
    assert len(TACTILE_FULL_NAMES) == 130


def test_dual_arm_tactile_avg_count():
    assert len(DUAL_ARM_TACTILE_AVG_FEATURE_NAMES) == 14


def test_dual_arm_tactile_fingertip_count():
    assert len(DUAL_ARM_TACTILE_FINGERTIP_FEATURE_NAMES) == 160


def test_dual_arm_tactile_full_count():
    assert len(DUAL_ARM_TACTILE_FULL_FEATURE_NAMES) == 260


def test_dual_arm_tactile_avg_has_both_sides():
    names = DUAL_ARM_TACTILE_AVG_FEATURE_NAMES
    left_names = [n for n in names if n.startswith("left.")]
    right_names = [n for n in names if n.startswith("right.")]
    assert len(left_names) == 7
    assert len(right_names) == 7


def test_no_duplicate_feature_names():
    assert len(set(DUAL_ARM_TACTILE_FULL_FEATURE_NAMES)) == 260
