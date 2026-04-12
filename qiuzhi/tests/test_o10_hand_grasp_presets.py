from pathlib import Path
import sys

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

from lerobot_play.utils.agibot_o10 import AGIBOT_O10_HAND_FEATURE_NAMES
from lerobot_play.utils.o10_hand_grasp_presets import (
    apply_hand_grasp_preset,
    normalize_hand_control_mode,
    normalize_hand_grasp_preset,
)


def test_apply_hand_grasp_preset_keeps_only_thumb_and_index_active():
    requested_joint_pos = [float(index + 100) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))]
    preset_joint_pos = [float(index) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))]

    filtered_joint_pos = apply_hand_grasp_preset(
        requested_joint_pos=requested_joint_pos,
        preset_joint_pos=preset_joint_pos,
        preset="pinch_index",
    )

    assert filtered_joint_pos == pytest.approx(
        [
            0.0,
            1.0,
            102.0,
            3.0,
            104.0,
            5.0,
            6.0,
            7.0,
            8.0,
            9.0,
        ]
    )


def test_apply_hand_grasp_preset_keeps_tripod_fingers_active():
    requested_joint_pos = [float(index + 10) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))]
    preset_joint_pos = [float(index) for index in range(len(AGIBOT_O10_HAND_FEATURE_NAMES))]

    filtered_joint_pos = apply_hand_grasp_preset(
        requested_joint_pos=requested_joint_pos,
        preset_joint_pos=preset_joint_pos,
        preset="tripod",
    )

    assert filtered_joint_pos == pytest.approx(
        [
            0.0,
            1.0,
            12.0,
            3.0,
            14.0,
            15.0,
            6.0,
            7.0,
            8.0,
            9.0,
        ]
    )


def test_normalize_hand_control_mode_rejects_unknown_value():
    with pytest.raises(ValueError, match="hand_control_mode"):
        normalize_hand_control_mode("unknown_mode")


def test_normalize_hand_grasp_preset_rejects_unknown_value():
    with pytest.raises(ValueError, match="hand_grasp_preset"):
        normalize_hand_grasp_preset("thumb_and_ring")
