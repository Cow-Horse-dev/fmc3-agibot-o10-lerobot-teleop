#!/usr/bin/env python3
"""MediaPipe 摄像头控制智元 O10 右手，带 OpenCV 图形界面。

用法：
    python tests/test_mediapipe_right_hand_control.py --no-hw   # 无硬件调试
    python tests/test_mediapipe_right_hand_control.py           # 连接右手
    python tests/test_mediapipe_right_hand_control.py --hand left --channel-id 0
"""

from __future__ import annotations

import argparse
import math
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        HandLandmarker,
        HandLandmarkerOptions,
        RunningMode,
    )
    from mediapipe.tasks.python.vision.hand_landmarker import HandLandmark
except ModuleNotFoundError as exc:
    if "pytest" in sys.modules and (exc.name or "").startswith("mediapipe"):
        import pytest

        pytest.skip("manual MediaPipe camera script requires mediapipe", allow_module_level=True)
    raise

REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_ROOT = (
    REPO_ROOT / "qiuzhi" / "lerobot_play_1.0.4" / "x86" / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)
if str(LEROBOT_PLAY_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_ROOT))

from lerobot_play.utils.agibot_o10 import (
    AgibotO10Hand,
    O10HandMapper,
)

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
MODEL_PATH = REPO_ROOT / "models" / "hand_landmarker.task"

_LM = HandLandmark

HAND_CONNECTIONS = [
    (_LM.WRIST, _LM.THUMB_CMC), (_LM.THUMB_CMC, _LM.THUMB_MCP),
    (_LM.THUMB_MCP, _LM.THUMB_IP), (_LM.THUMB_IP, _LM.THUMB_TIP),
    (_LM.WRIST, _LM.INDEX_FINGER_MCP), (_LM.INDEX_FINGER_MCP, _LM.INDEX_FINGER_PIP),
    (_LM.INDEX_FINGER_PIP, _LM.INDEX_FINGER_DIP), (_LM.INDEX_FINGER_DIP, _LM.INDEX_FINGER_TIP),
    (_LM.WRIST, _LM.MIDDLE_FINGER_MCP), (_LM.MIDDLE_FINGER_MCP, _LM.MIDDLE_FINGER_PIP),
    (_LM.MIDDLE_FINGER_PIP, _LM.MIDDLE_FINGER_DIP), (_LM.MIDDLE_FINGER_DIP, _LM.MIDDLE_FINGER_TIP),
    (_LM.WRIST, _LM.RING_FINGER_MCP), (_LM.RING_FINGER_MCP, _LM.RING_FINGER_PIP),
    (_LM.RING_FINGER_PIP, _LM.RING_FINGER_DIP), (_LM.RING_FINGER_DIP, _LM.RING_FINGER_TIP),
    (_LM.WRIST, _LM.PINKY_MCP), (_LM.PINKY_MCP, _LM.PINKY_PIP),
    (_LM.PINKY_PIP, _LM.PINKY_DIP), (_LM.PINKY_DIP, _LM.PINKY_TIP),
    (_LM.INDEX_FINGER_MCP, _LM.MIDDLE_FINGER_MCP),
    (_LM.MIDDLE_FINGER_MCP, _LM.RING_FINGER_MCP),
    (_LM.RING_FINGER_MCP, _LM.PINKY_MCP),
]

JOINT_SHORT_NAMES = [
    "T-roll", "T-yaw", "T-pitch",
    "I-yaw", "I-pitch", "M-pitch",
    "R-yaw", "R-pitch", "P-yaw", "P-pitch",
]
BAR_PANEL_W = 280


def ensure_model() -> str:
    if MODEL_PATH.exists():
        return str(MODEL_PATH)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading hand_landmarker model to {MODEL_PATH} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Download complete.")
    return str(MODEL_PATH)


def _vec(a, b) -> np.ndarray:
    return np.array([b.x - a.x, b.y - a.y, b.z - a.z], dtype=float)


def _angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    cos = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9)
    return math.degrees(math.acos(float(np.clip(cos, -1.0, 1.0))))


def _bend(lm, mcp, pip, tip) -> float:
    v1 = _vec(lm[mcp], lm[pip])
    v2 = _vec(lm[pip], lm[tip])
    return _angle_between(v1, v2)


def _spread(lm, a, b, w) -> float:
    v1 = _vec(lm[w], lm[a])
    v2 = _vec(lm[w], lm[b])
    return _angle_between(v1, v2)


def mediapipe_to_glove_angles(lm) -> list[float]:
    W = _LM.WRIST
    # thumb_cm_roll: 拇指旋转，张开时角度大 → 内收时需要反转
    raw_roll = _spread(lm, _LM.THUMB_MCP, _LM.MIDDLE_FINGER_MCP, _LM.THUMB_CMC)
    thumb_roll = max(0, 40 - raw_roll) * 0.9
    # thumb_cm_yaw: 拇指外展 → 内收时 spread 变小，需要反转
    raw_yaw = _spread(lm, _LM.THUMB_CMC, _LM.INDEX_FINGER_MCP, W)
    thumb_yaw = max(0, 50 - raw_yaw) * 0.8
    # thumb_cm_pitch: 拇指弯曲 — 弯曲越大角度越大，方向正确
    thumb_pitch = _bend(lm, _LM.THUMB_CMC, _LM.THUMB_MCP, _LM.THUMB_IP)
    # 四指
    index_yaw   = _spread(lm, _LM.INDEX_FINGER_MCP, _LM.MIDDLE_FINGER_MCP, W) * 0.5
    index_pitch = _bend(lm, _LM.INDEX_FINGER_MCP, _LM.INDEX_FINGER_PIP, _LM.INDEX_FINGER_TIP)
    middle_pitch = _bend(lm, _LM.MIDDLE_FINGER_MCP, _LM.MIDDLE_FINGER_PIP, _LM.MIDDLE_FINGER_TIP)
    ring_yaw    = _spread(lm, _LM.RING_FINGER_MCP, _LM.MIDDLE_FINGER_MCP, W) * 0.5
    ring_pitch  = _bend(lm, _LM.RING_FINGER_MCP, _LM.RING_FINGER_PIP, _LM.RING_FINGER_TIP)
    pinky_yaw   = _spread(lm, _LM.PINKY_MCP, _LM.RING_FINGER_MCP, W) * 0.5
    pinky_pitch = _bend(lm, _LM.PINKY_MCP, _LM.PINKY_PIP, _LM.PINKY_TIP)
    return [thumb_roll, thumb_yaw, thumb_pitch, index_yaw, index_pitch,
            middle_pitch, ring_yaw, ring_pitch, pinky_yaw, pinky_pitch]


def draw_landmarks(frame: np.ndarray, lm_list, w: int, h: int) -> None:
    pts = [(int(l.x * w), int(l.y * h)) for l in lm_list]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (0, 255, 128), 2)
    for pt in pts:
        cv2.circle(frame, pt, 4, (0, 0, 255), -1)


def draw_joint_bars(panel: np.ndarray, angles_rad: list[float]) -> None:
    limits = [37, 30, 60, 30, 81, 81, 20, 81, 30, 100]
    h, w = panel.shape[:2]
    row_h = h // 11
    bar_max_w = w - 120
    cv2.putText(panel, "Joint Angles", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
    for i, (name, rad) in enumerate(zip(JOINT_SHORT_NAMES, angles_rad)):
        deg = math.degrees(abs(rad))
        ratio = min(deg / (limits[i] + 1e-9), 1.0)
        y = (i + 1) * row_h + row_h // 2
        cv2.putText(panel, name, (4, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)
        cv2.rectangle(panel, (80, y - 8), (80 + bar_max_w, y + 8), (50, 50, 50), -1)
        fill_w = int(ratio * bar_max_w)
        color = (0, int(200 * (1 - ratio)), int(200 * ratio))
        if fill_w > 0:
            cv2.rectangle(panel, (80, y - 8), (80 + fill_w, y + 8), color, -1)
        cv2.putText(panel, f"{deg:4.0f}", (80 + bar_max_w + 4, y + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (220, 220, 220), 1)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MediaPipe 控制智元 O10 手")
    p.add_argument("--hand", choices=["left", "right"], default="right")
    p.add_argument("--camera", default="/dev/video14",
                    help="摄像头设备路径或索引号，如 /dev/video14 或 0")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--device-id", type=int, default=1)
    p.add_argument("--canfd-id", type=int, default=0)
    p.add_argument("--channel-id", type=int, default=None)
    p.add_argument("--no-hw", action="store_true", help="不连接硬件，仅显示图形界面")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    handedness = args.hand
    model_path = ensure_model()
    mapper = O10HandMapper(handedness=handedness)

    hand_hw: AgibotO10Hand | None = None
    if not args.no_hw:
        hand_hw = AgibotO10Hand(
            handedness=handedness, channel_mode="multiChannel",
            device_id=args.device_id, canfd_id=args.canfd_id,
            channel_id=args.channel_id,
        )
        try:
            print(f"Connecting {handedness} hand...")
            hand_hw.connect()
            print("Hand connected.")
        except Exception as e:
            print(f"[WARN] Hand connect failed ({e}), running in --no-hw mode.")
            hand_hw = None

    cam_src = int(args.camera) if args.camera.isdigit() else args.camera
    cap = cv2.VideoCapture(cam_src, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    if not cap.isOpened():
        print(f"Cannot open camera {args.camera}")
        return 1

    latest_result = [None]
    def _on_result(result, image, timestamp_ms):
        latest_result[0] = result

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=RunningMode.LIVE_STREAM,
        num_hands=1,
        min_hand_detection_confidence=0.6,
        min_tracking_confidence=0.5,
        result_callback=_on_result,
    )
    landmarker = HandLandmarker.create_from_options(options)

    angles_rad: list[float] = [0.0] * 10
    fps_t = time.monotonic()
    fps = 0.0
    frame_count = 0
    hw_status = "no-hw" if hand_hw is None else "connected"
    t0 = time.monotonic()
    target_w, target_h = args.width, args.height
    print("Press 'q' to quit.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)
            h0, w0 = frame.shape[:2]
            if w0 != target_w or h0 != target_h:
                frame = cv2.resize(frame, (target_w, target_h))
            cam_h, cam_w = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts_ms = int((time.monotonic() - t0) * 1000)
            landmarker.detect_async(mp_image, ts_ms)

            detected = False
            result = latest_result[0]
            if result and result.hand_landmarks:
                lm_list = result.hand_landmarks[0]
                draw_landmarks(frame, lm_list, cam_w, cam_h)
                glove_angles = mediapipe_to_glove_angles(lm_list)
                angles_rad = mapper.map(glove_angles)
                detected = True

            if detected and hand_hw is not None:
                try:
                    hand_hw.write_active_joint_angles(angles_rad)
                except Exception as e:
                    hw_status = f"err:{e}"

            frame_count += 1
            now = time.monotonic()
            if now - fps_t >= 0.5:
                fps = frame_count / (now - fps_t)
                frame_count = 0
                fps_t = now

            panel = np.zeros((cam_h, BAR_PANEL_W, 3), dtype=np.uint8)
            draw_joint_bars(panel, angles_rad)
            canvas = np.hstack([frame, panel])

            hand_str = "DETECTED" if detected else "no hand"
            status = f"FPS:{fps:.1f}  hand:{handedness}  {hand_str}  hw:{hw_status}"
            cv2.putText(canvas, status, (8, cam_h - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 220), 1)
            cv2.imshow("MediaPipe -> O10 Hand", canvas)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        landmarker.close()
        cv2.destroyAllWindows()
        if hand_hw is not None:
            hand_hw.disconnect()
            print("Hand disconnected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
