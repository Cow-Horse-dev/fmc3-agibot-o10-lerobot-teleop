from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DUAL_ARM_SRC_FILE = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/robots/pico_follower_dual_arm_agibot_o10/airbot_pico_follower_dual_arm_agibot_o10.py"
)
HAND_SRC_FILE = (
    REPO_ROOT
    / "lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any"
    / "lerobot_play/utils/agibot_o10.py"
)


def test_dual_arm_robot_source_uses_cached_tactile_reads():
    source = DUAL_ARM_SRC_FILE.read_text(encoding="utf-8")

    assert "read_tactile_full_cached()" in source


def test_agibot_hand_source_defines_cached_tactile_helpers():
    source = HAND_SRC_FILE.read_text(encoding="utf-8")

    assert "def read_tactile_full_cached(" in source
