from __future__ import annotations

from typing import Sequence

from .agibot_o10 import AGIBOT_O10_HAND_FEATURE_NAMES


HAND_CONTROL_MODE_FULL_HAND = "full_hand"
HAND_CONTROL_MODE_GRASP_PRESET = "grasp_preset"

HAND_GRASP_PRESET_ACTIVE_JOINTS = {
    "pinch_index": {
        "thumb_cm_pitch.pos",
        "index_mp_pitch.pos",
    },
    "pinch_middle": {
        "thumb_cm_pitch.pos",
        "middle_mp_pitch.pos",
    },
    "tripod": {
        "thumb_cm_pitch.pos",
        "index_mp_pitch.pos",
        "middle_mp_pitch.pos",
    },
}


def normalize_hand_control_mode(mode: str | None) -> str:
    normalized_mode = str(mode or HAND_CONTROL_MODE_FULL_HAND).strip().lower()
    if normalized_mode not in {
        HAND_CONTROL_MODE_FULL_HAND,
        HAND_CONTROL_MODE_GRASP_PRESET,
    }:
        raise ValueError(
            "Unsupported Agibot O10 hand_control_mode: "
            f"{mode}. Expected one of: full_hand, grasp_preset"
        )
    return normalized_mode


def normalize_hand_grasp_preset(preset: str | None) -> str:
    normalized_preset = str(preset or "pinch_index").strip().lower()
    if normalized_preset not in HAND_GRASP_PRESET_ACTIVE_JOINTS:
        raise ValueError(
            "Unsupported Agibot O10 hand_grasp_preset: "
            f"{preset}. Expected one of: {', '.join(HAND_GRASP_PRESET_ACTIVE_JOINTS)}"
        )
    return normalized_preset


def apply_hand_grasp_preset(
    requested_joint_pos: Sequence[float],
    preset_joint_pos: Sequence[float],
    preset: str,
) -> list[float]:
    if len(requested_joint_pos) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
        raise ValueError(
            f"requested_joint_pos must contain {len(AGIBOT_O10_HAND_FEATURE_NAMES)} values, "
            f"got {len(requested_joint_pos)}"
        )
    if len(preset_joint_pos) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
        raise ValueError(
            f"preset_joint_pos must contain {len(AGIBOT_O10_HAND_FEATURE_NAMES)} values, "
            f"got {len(preset_joint_pos)}"
        )

    normalized_preset = normalize_hand_grasp_preset(preset)
    active_joint_names = HAND_GRASP_PRESET_ACTIVE_JOINTS[normalized_preset]

    filtered_joint_pos: list[float] = []
    for feature_name, requested_value, reset_value in zip(
        AGIBOT_O10_HAND_FEATURE_NAMES,
        requested_joint_pos,
        preset_joint_pos,
        strict=True,
    ):
        filtered_joint_pos.append(
            float(requested_value)
            if feature_name in active_joint_names
            else float(reset_value)
        )

    return filtered_joint_pos
