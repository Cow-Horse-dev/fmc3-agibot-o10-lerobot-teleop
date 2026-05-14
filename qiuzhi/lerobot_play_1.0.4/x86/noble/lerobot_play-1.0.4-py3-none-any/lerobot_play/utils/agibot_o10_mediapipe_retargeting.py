from __future__ import annotations

import math
from typing import Sequence

import numpy as np


FINGER_LANDMARKS = {
    "thumb": (1, 2, 3, 4),
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}
FINGER_ORDER = ("thumb", "index", "middle", "ring", "pinky")
O10_GLOVE_LIMITS_DEG = (37.0, 30.0, 60.0, 30.0, 81.0, 81.0, 20.0, 81.0, 30.0, 100.0)


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-8:
        return np.zeros(3, dtype=np.float64)
    return vector / norm


def _angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 < 1e-8 or n2 < 1e-8:
        return 0.0
    cosine = float(np.dot(v1, v2) / (n1 * n2))
    return float(np.arccos(np.clip(cosine, -1.0, 1.0)))


def _project_onto_plane(vector: np.ndarray, normal: np.ndarray) -> np.ndarray:
    return vector - np.dot(vector, normal) * normal


def _abduction_angle(v_finger: np.ndarray, v_ref: np.ndarray, palm_normal: np.ndarray) -> float:
    return _angle_between(
        _project_onto_plane(v_finger, palm_normal),
        _project_onto_plane(v_ref, palm_normal),
    )


def _canonicalize_landmarks(
    landmarks: np.ndarray | Sequence[Sequence[float]],
    handedness: str,
) -> np.ndarray:
    lm = np.asarray(landmarks, dtype=np.float64)
    if lm.shape != (21, 3):
        raise ValueError(f"Expected landmarks shape (21, 3), got {lm.shape}")
    if handedness == "left":
        mirrored = lm.copy()
        mirrored[:, 0] *= -1.0
        return mirrored
    if handedness != "right":
        raise ValueError(f"Unsupported handedness: {handedness!r}")
    return lm.copy()


def _build_palm_frame(landmarks: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    wrist = landmarks[0]
    lateral = landmarks[17] - landmarks[5]
    distal = landmarks[9] - wrist

    palm_x = _normalize(lateral)
    palm_y = _normalize(distal)
    palm_z = _normalize(np.cross(palm_x, palm_y))
    if np.linalg.norm(palm_z) < 1e-8:
        palm_z = _normalize(np.cross(landmarks[5] - wrist, landmarks[17] - wrist))
    palm_y = _normalize(np.cross(palm_z, palm_x))
    return palm_x, palm_y, palm_z


def _plane_angle(landmarks: np.ndarray, origin: int, a: int, b: int, normal: np.ndarray) -> float:
    va = landmarks[a] - landmarks[origin]
    vb = landmarks[b] - landmarks[origin]
    return _abduction_angle(va, vb, normal)


def _finger_direction_yaw_deg(
    landmarks: np.ndarray,
    finger_mcp: int,
    finger_pip: int,
    ref_mcp: int,
    ref_pip: int,
    palm_normal: np.ndarray,
    scale: float = 0.55,
) -> float:
    finger_direction = landmarks[finger_pip] - landmarks[finger_mcp]
    reference_direction = landmarks[ref_pip] - landmarks[ref_mcp]
    return math.degrees(_abduction_angle(finger_direction, reference_direction, palm_normal)) * scale


def _composite_flex_deg(angles: Sequence[float], start_index: int) -> float:
    mcp = math.degrees(angles[start_index + 1])
    pip = math.degrees(angles[start_index + 2])
    dip = math.degrees(angles[start_index + 3])
    return 0.5 * mcp + 0.35 * pip + 0.15 * dip


def _thumb_pitch_deg(angles: Sequence[float]) -> float:
    mcp = math.degrees(angles[1])
    pip = math.degrees(angles[2])
    dip = math.degrees(angles[3])
    return 0.35 * mcp + 0.40 * pip + 0.25 * dip


def _thumb_roll_deg(landmarks: np.ndarray, palm_normal: np.ndarray) -> float:
    thumb_direction = _normalize(landmarks[4] - landmarks[1])
    elevation = math.degrees(math.asin(float(np.clip(np.dot(thumb_direction, palm_normal), -1.0, 1.0))))
    return max(0.0, abs(elevation) * 0.95)


def _thumb_yaw_deg(landmarks: np.ndarray, palm_normal: np.ndarray) -> float:
    thumb_base_ray = landmarks[2] - landmarks[1]
    palm_forward = landmarks[9] - landmarks[0]
    angle = math.degrees(_abduction_angle(thumb_base_ray, palm_forward, palm_normal))
    return max(0.0, (60.0 - angle) * 0.55)


def _thumb_pinch_strength(landmarks: np.ndarray) -> float:
    thumb_tip = landmarks[4]
    finger_tips = (landmarks[8], landmarks[12], landmarks[16], landmarks[20])
    min_distance = min(float(np.linalg.norm(thumb_tip - tip)) for tip in finger_tips)
    # Distances around 1.8 look open in our normalized hand frame; below 0.45 is a clear pinch.
    return float(np.clip((1.8 - min_distance) / (1.8 - 0.45), 0.0, 1.0))


def _clip_output(values: Sequence[float]) -> list[float]:
    return [
        max(0.0, min(float(value), limit))
        for value, limit in zip(values, O10_GLOVE_LIMITS_DEG)
    ]


def compute_joint_angles(landmarks: np.ndarray | Sequence[Sequence[float]]) -> list[float]:
    """Compute 20 finger joint angles from 21 3D hand landmarks."""
    lm = np.asarray(landmarks, dtype=np.float64)
    if lm.shape != (21, 3):
        raise ValueError(f"Expected landmarks shape (21, 3), got {lm.shape}")

    wrist = lm[0]
    palm_v1 = lm[5] - wrist
    palm_v2 = lm[17] - wrist
    palm_normal = _normalize(np.cross(palm_v1, palm_v2))
    mid_ref = lm[9] - wrist

    angles: list[float] = []
    for finger in FINGER_ORDER:
        mcp_i, pip_i, dip_i, tip_i = FINGER_LANDMARKS[finger]
        v_wrist_mcp = lm[mcp_i] - wrist
        v_mcp_pip = lm[pip_i] - lm[mcp_i]
        v_pip_dip = lm[dip_i] - lm[pip_i]
        v_dip_tip = lm[tip_i] - lm[dip_i]

        abd = _abduction_angle(v_wrist_mcp, mid_ref, palm_normal)
        flex_mcp = _angle_between(v_wrist_mcp, v_mcp_pip)
        flex_pip = _angle_between(v_mcp_pip, v_pip_dip)
        flex_dip = _angle_between(v_pip_dip, v_dip_tip)
        angles.extend((abd, flex_mcp, flex_pip, flex_dip))

    return angles


def mediapipe_landmarks_to_o10_glove_degrees(
    landmarks: np.ndarray | Sequence[Sequence[float]],
    handedness: str = "right",
) -> list[float]:
    """Convert MediaPipe hand landmarks to the 10 glove-like O10 input channels."""
    canonical = _canonicalize_landmarks(landmarks, handedness)
    palm_x, palm_y, palm_normal = _build_palm_frame(canonical)
    del palm_x, palm_y  # reserved for future palm-frame tuning

    joint_angles = compute_joint_angles(canonical)
    pinch_strength = _thumb_pinch_strength(canonical)

    thumb_roll = _thumb_roll_deg(canonical, palm_normal) + 20.0 * pinch_strength
    thumb_yaw = _thumb_yaw_deg(canonical, palm_normal)
    thumb_pitch = _thumb_pitch_deg(joint_angles) + 12.0 * pinch_strength

    index_yaw = _finger_direction_yaw_deg(canonical, 5, 6, 9, 10, palm_normal)
    index_pitch = _composite_flex_deg(joint_angles, 4)
    middle_pitch = _composite_flex_deg(joint_angles, 8)
    ring_yaw = _finger_direction_yaw_deg(canonical, 13, 14, 9, 10, palm_normal)
    ring_pitch = _composite_flex_deg(joint_angles, 12)
    pinky_yaw = _finger_direction_yaw_deg(canonical, 17, 18, 13, 14, palm_normal)
    pinky_pitch = _composite_flex_deg(joint_angles, 16)

    return _clip_output(
        (
            thumb_roll,
            thumb_yaw,
            thumb_pitch,
            index_yaw,
            index_pitch,
            middle_pitch,
            ring_yaw,
            ring_pitch,
            pinky_yaw,
            pinky_pitch,
        )
    )


def select_preferred_hand_landmarks(result, hand_index: int = 0) -> np.ndarray | None:
    """Prefer MediaPipe world landmarks and fall back to image-space landmarks."""
    for attribute_name in ("hand_world_landmarks", "hand_landmarks"):
        landmark_sets = getattr(result, attribute_name, None)
        if landmark_sets and len(landmark_sets) > hand_index:
            landmarks = landmark_sets[hand_index]
            if len(landmarks) != 21:
                continue
            return np.asarray(
                [[point.x, point.y, point.z] for point in landmarks],
                dtype=np.float64,
            )
    return None
