#!/usr/bin/env python3
"""读取双臂当前关节位置，结合手势 open 姿态，生成 reset pose JSON。

为每种手势（pinch、tripod）各生成一组左右 reset pose 文件，
臂关节从真机读取，手部关节使用预定义手势的 open 状态。

Usage:
    # 生成所有手势的 reset pose（pinch + tripod）
    python scripts/tools/save_gesture_reset_poses.py

    # 只生成 pinch
    python scripts/tools/save_gesture_reset_poses.py --gesture pinch

    # 自定义 CAN 口
    python scripts/tools/save_gesture_reset_poses.py --left-port can0 --right-port can1

    # 跳过真机，用现有臂位置文件中的值
    python scripts/tools/save_gesture_reset_poses.py --arm-from-file configs/o10_left_reset_pose.new.json configs/o10_right_reset_pose.new.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any")
from lerobot_play.utils.agibot_o10 import (  # noqa: E402
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AGIBOT_O10_TRIGGER_GESTURES,
)

ARM_DOF = len(AGIBOT_O10_ARM_FEATURE_NAMES)
OUTPUT_DIR = Path("configs/reset_poses")


def _create_arm():
    import airbot_hardware_py as ah

    return ah.Play.create(
        ah.MotorType.OD,
        ah.MotorType.OD,
        ah.MotorType.OD,
        ah.MotorType.DM,
        ah.MotorType.DM,
        ah.MotorType.DM,
        ah.EEFType.NA,
        ah.MotorType.NA,
    )


def _read_arm_joint_positions(port: str) -> list[float]:
    import airbot_hardware_py as ah

    executor = ah.create_asio_executor(8)
    io_context = executor.get_io_context()
    arm = _create_arm()
    print(f"  Connecting arm on {port}...")
    if not arm.init(io_context, port, 250):
        raise RuntimeError(f"Failed to initialize arm on {port}")
    try:
        time.sleep(0.1)
        return [float(v) for v in list(arm.state().pos)[:ARM_DOF]]
    finally:
        arm.uninit()


def _load_arm_from_file(path: str) -> list[float]:
    data = json.loads(Path(path).expanduser().read_text())
    jv = data["groups"]["arm"]["joint_values"]
    return [jv[name] for name in AGIBOT_O10_ARM_FEATURE_NAMES]


def _build_reset_payload(arm_pos: list[float], hand_pos: list[float]) -> dict:
    return {
        "groups": {
            "arm": {
                "feature_names": list(AGIBOT_O10_ARM_FEATURE_NAMES),
                "joint_values": dict(zip(AGIBOT_O10_ARM_FEATURE_NAMES, arm_pos, strict=True)),
            },
            "hand": {
                "feature_names": list(AGIBOT_O10_HAND_FEATURE_NAMES),
                "joint_values": dict(zip(AGIBOT_O10_HAND_FEATURE_NAMES, hand_pos, strict=True)),
            },
        }
    }


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成手势 reset pose JSON（臂从真机读取，手用手势 open 姿态）")
    parser.add_argument("--gesture", choices=sorted(AGIBOT_O10_TRIGGER_GESTURES), default=None,
                        help="只生成指定手势，默认全部生成")
    parser.add_argument("--left-port", default="can0")
    parser.add_argument("--right-port", default="can1")
    parser.add_argument("--arm-from-file", nargs=2, metavar=("LEFT_JSON", "RIGHT_JSON"),
                        help="跳过真机，从现有 JSON 读取臂位置")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    gestures = [args.gesture] if args.gesture else sorted(AGIBOT_O10_TRIGGER_GESTURES)

    if args.arm_from_file:
        print(f"从文件读取臂位置: {args.arm_from_file}")
        left_arm = _load_arm_from_file(args.arm_from_file[0])
        right_arm = _load_arm_from_file(args.arm_from_file[1])
    else:
        print("从真机读取臂位置...")
        left_arm = _read_arm_joint_positions(args.left_port)
        right_arm = _read_arm_joint_positions(args.right_port)

    print(f"\n左臂关节: {[f'{v:+.4f}' for v in left_arm]}")
    print(f"右臂关节: {[f'{v:+.4f}' for v in right_arm]}")

    for gesture_name in gestures:
        gesture = AGIBOT_O10_TRIGGER_GESTURES[gesture_name]
        left_hand = gesture["left"]["open"]
        right_hand = gesture["right"]["open"]

        left_path = args.output_dir / f"o10_left_reset_{gesture_name}.json"
        right_path = args.output_dir / f"o10_right_reset_{gesture_name}.json"

        _save(left_path, _build_reset_payload(left_arm, left_hand))
        _save(right_path, _build_reset_payload(right_arm, right_hand))

        print(f"\n[{gesture_name}]")
        print(f"  左手 open: {left_hand}")
        print(f"  右手 open: {right_hand}")
        print(f"  -> {left_path}")
        print(f"  -> {right_path}")

    print(f"\n完成！文件保存在 {args.output_dir}/")
    print("使用方法：YAML 配置中使用 reset_poses_path 指向集中式 JSON（如 configs/reset_poses/o10_dual_reset.json），"
          "并用 reset_gesture 指定手势名称（如 pinch）。")


if __name__ == "__main__":
    main()
