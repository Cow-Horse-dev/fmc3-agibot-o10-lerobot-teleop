import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
LEROBOT_PLAY_ROOT = (
    REPO_ROOT / "qiuzhi" / "lerobot_play_1.0.4" / "x86" / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)
if str(LEROBOT_PLAY_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_ROOT))

from lerobot_play.utils.agibot_o10_mediapipe_retargeting import (
    compute_joint_angles,
    mediapipe_landmarks_to_o10_glove_degrees,
    select_preferred_hand_landmarks,
)


def _open_hand_landmarks() -> np.ndarray:
    landmarks = np.zeros((21, 3), dtype=np.float64)
    landmarks[0] = [0.0, 0.0, 0.0]

    landmarks[1] = [-1.00, 0.20, 0.00]
    landmarks[2] = [-1.35, 0.45, 0.00]
    landmarks[3] = [-1.60, 0.75, 0.00]
    landmarks[4] = [-1.82, 1.00, 0.00]

    landmarks[5] = [-0.45, 0.70, 0.00]
    landmarks[6] = [-0.45, 1.45, 0.00]
    landmarks[7] = [-0.45, 2.05, 0.00]
    landmarks[8] = [-0.45, 2.55, 0.00]

    landmarks[9] = [0.00, 0.70, 0.00]
    landmarks[10] = [0.00, 1.55, 0.00]
    landmarks[11] = [0.00, 2.25, 0.00]
    landmarks[12] = [0.00, 2.85, 0.00]

    landmarks[13] = [0.42, 0.70, 0.00]
    landmarks[14] = [0.42, 1.42, 0.00]
    landmarks[15] = [0.42, 2.00, 0.00]
    landmarks[16] = [0.42, 2.48, 0.00]

    landmarks[17] = [0.84, 0.66, 0.00]
    landmarks[18] = [0.84, 1.28, 0.00]
    landmarks[19] = [0.84, 1.80, 0.00]
    landmarks[20] = [0.84, 2.22, 0.00]
    return landmarks


def _curl_index_finger(landmarks: np.ndarray) -> np.ndarray:
    curled = landmarks.copy()
    curled[6] = [-0.45, 1.15, 0.35]
    curled[7] = [-0.45, 1.05, 0.95]
    curled[8] = [-0.45, 0.95, 1.35]
    return curled


def _spread_index_finger(landmarks: np.ndarray) -> np.ndarray:
    spread = landmarks.copy()
    spread[6] = [-0.82, 1.35, 0.00]
    spread[7] = [-1.08, 1.96, 0.00]
    spread[8] = [-1.30, 2.44, 0.00]
    return spread


def _oppose_thumb(landmarks: np.ndarray) -> np.ndarray:
    opposed = landmarks.copy()
    opposed[2] = [-0.95, 0.55, 0.00]
    opposed[3] = [-0.55, 0.75, 0.00]
    opposed[4] = [-0.10, 0.95, 0.00]
    return opposed


def _pinch_thumb_index(landmarks: np.ndarray) -> np.ndarray:
    pinched = _oppose_thumb(landmarks)
    pinched[6] = [-0.35, 1.20, 0.25]
    pinched[7] = [-0.25, 1.00, 0.45]
    pinched[8] = [-0.15, 0.92, 0.48]
    return pinched


def test_compute_joint_angles_returns_20_values():
    angles = compute_joint_angles(_open_hand_landmarks())

    assert len(angles) == 20
    assert all(isinstance(value, float) for value in angles)


def test_compute_joint_angles_keeps_straight_index_pip_and_dip_near_zero():
    angles = compute_joint_angles(_open_hand_landmarks())

    assert abs(angles[6]) < 0.05
    assert abs(angles[7]) < 0.05


def test_mediapipe_landmarks_to_o10_glove_degrees_increases_index_pitch_for_curl():
    open_hand = _open_hand_landmarks()
    curled_hand = _curl_index_finger(open_hand)

    open_degrees = mediapipe_landmarks_to_o10_glove_degrees(open_hand, handedness="right")
    curled_degrees = mediapipe_landmarks_to_o10_glove_degrees(curled_hand, handedness="right")

    assert len(open_degrees) == 10
    assert len(curled_degrees) == 10
    assert curled_degrees[4] > open_degrees[4] + 15.0
    assert curled_degrees[4] <= 81.0


def test_mediapipe_landmarks_to_o10_glove_degrees_increases_index_yaw_for_spread():
    open_hand = _open_hand_landmarks()
    spread_hand = _spread_index_finger(open_hand)

    open_degrees = mediapipe_landmarks_to_o10_glove_degrees(open_hand, handedness="right")
    spread_degrees = mediapipe_landmarks_to_o10_glove_degrees(spread_hand, handedness="right")

    assert spread_degrees[3] > open_degrees[3] + 5.0
    assert spread_degrees[3] <= 30.0


def test_mediapipe_landmarks_to_o10_glove_degrees_increases_thumb_yaw_for_opposition():
    open_hand = _open_hand_landmarks()
    opposed_thumb = _oppose_thumb(open_hand)

    open_degrees = mediapipe_landmarks_to_o10_glove_degrees(open_hand, handedness="right")
    opposed_degrees = mediapipe_landmarks_to_o10_glove_degrees(opposed_thumb, handedness="right")

    assert opposed_degrees[1] > open_degrees[1] + 8.0
    assert opposed_degrees[1] <= 30.0


def test_thumb_grasp_pose_increases_thumb_roll_or_pitch_beyond_plain_opposition():
    open_hand = _open_hand_landmarks()
    opposed_thumb = _oppose_thumb(open_hand)
    pinched_thumb = _pinch_thumb_index(open_hand)

    opposed_degrees = mediapipe_landmarks_to_o10_glove_degrees(opposed_thumb, handedness="right")
    pinched_degrees = mediapipe_landmarks_to_o10_glove_degrees(pinched_thumb, handedness="right")

    assert (
        pinched_degrees[0] > opposed_degrees[0] + 8.0
        or pinched_degrees[2] > opposed_degrees[2] + 6.0
    )


def test_select_preferred_hand_landmarks_uses_world_landmarks_first():
    world_landmarks = [[SimpleNamespace(x=1.0, y=2.0, z=3.0)] * 21]
    image_landmarks = [[SimpleNamespace(x=4.0, y=5.0, z=6.0)] * 21]
    result = SimpleNamespace(
        hand_world_landmarks=world_landmarks,
        hand_landmarks=image_landmarks,
    )

    selected = select_preferred_hand_landmarks(result)

    assert math.isclose(selected[0][0], 1.0)
    assert math.isclose(selected[0][1], 2.0)
    assert math.isclose(selected[0][2], 3.0)


def test_select_preferred_hand_landmarks_falls_back_to_image_landmarks():
    image_landmarks = [[SimpleNamespace(x=4.0, y=5.0, z=6.0)] * 21]
    result = SimpleNamespace(
        hand_world_landmarks=[],
        hand_landmarks=image_landmarks,
    )

    selected = select_preferred_hand_landmarks(result)

    assert math.isclose(selected[0][0], 4.0)
    assert math.isclose(selected[0][1], 5.0)
    assert math.isclose(selected[0][2], 6.0)
