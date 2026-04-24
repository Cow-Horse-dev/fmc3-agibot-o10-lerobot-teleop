#!/usr/bin/env python3
"""Read current dual-arm O10 joint angles and save reset pose JSON files.

Usage:
    python scripts/tools/save_dual_reset_pose.py
    python scripts/tools/save_dual_reset_pose.py --left-port can0 --right-port can1
    python scripts/tools/save_dual_reset_pose.py \
        --left-output configs/o10_left_reset_pose.new.json \
        --right-output configs/o10_right_reset_pose.new.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import airbot_hardware_py as ah

sys.path.insert(0, "qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any")
from lerobot_play.utils.agibot_o10 import (  # noqa: E402
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AgibotO10Hand,
)

ARM_DOF = len(AGIBOT_O10_ARM_FEATURE_NAMES)
ZERO_HAND_POS = [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)


def _create_arm() -> ah.Play:
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


def _build_reset_payload(arm_pos: list[float], hand_pos: list[float]) -> dict:
    return {
        "groups": {
            "arm": {
                "feature_names": list(AGIBOT_O10_ARM_FEATURE_NAMES),
                "joint_values": {
                    name: value
                    for name, value in zip(AGIBOT_O10_ARM_FEATURE_NAMES, arm_pos, strict=True)
                },
            },
            "hand": {
                "feature_names": list(AGIBOT_O10_HAND_FEATURE_NAMES),
                "joint_values": {
                    name: value
                    for name, value in zip(AGIBOT_O10_HAND_FEATURE_NAMES, hand_pos, strict=True)
                },
            },
        }
    }


def _save_reset_file(output_path: str, payload: dict) -> None:
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _read_arm_joint_positions(port: str) -> list[float]:
    executor = ah.create_asio_executor(8)
    io_context = executor.get_io_context()
    arm = _create_arm()

    print(f"Connecting arm on {port}...")
    if not arm.init(io_context, port, 250):
        raise RuntimeError(f"Failed to initialize arm on {port}")

    try:
        time.sleep(0.1)
        return [float(value) for value in list(arm.state().pos)[:ARM_DOF]]
    finally:
        arm.uninit()


def _read_hand_joint_positions(
    handedness: str,
    *,
    channel_mode: str,
    device_id: int,
    canfd_id: int,
    channel_id: int | None,
) -> list[float]:
    hand = AgibotO10Hand(
        handedness=handedness,
        channel_mode=channel_mode,
        device_id=device_id,
        canfd_id=canfd_id,
        channel_id=channel_id,
    )
    print(f"Connecting {handedness} hand...")
    hand.connect()
    try:
        time.sleep(0.1)
        return [float(value) for value in hand.read_active_joint_angles()]
    finally:
        hand.disconnect()


def _print_joint_summary(side: str, arm_pos: list[float], hand_pos: list[float]) -> None:
    print(f"\nCurrent {side} arm joints:")
    for name, value in zip(AGIBOT_O10_ARM_FEATURE_NAMES, arm_pos, strict=True):
        print(f"  {name:>25s}: {value:+.6f}")
    print(f"\nCurrent {side} hand joints:")
    for name, value in zip(AGIBOT_O10_HAND_FEATURE_NAMES, hand_pos, strict=True):
        print(f"  {name:>25s}: {value:+.6f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Save current dual-arm O10 joint angles as reset pose JSON files"
    )
    parser.add_argument("--left-output", type=str, default="configs/o10_left_reset_pose.json")
    parser.add_argument("--right-output", type=str, default="configs/o10_right_reset_pose.json")
    parser.add_argument("--left-port", type=str, default="can0")
    parser.add_argument("--right-port", type=str, default="can1")
    parser.add_argument("--channel-mode", type=str, default="multiChannel")
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument("--canfd-id", type=int, default=0)
    parser.add_argument("--left-channel-id", type=int, default=None)
    parser.add_argument("--right-channel-id", type=int, default=None)
    parser.add_argument(
        "--arm-only",
        action="store_true",
        help="Skip hand hardware reads and write zero hand joints as placeholders",
    )
    args = parser.parse_args()

    left_arm_pos = _read_arm_joint_positions(args.left_port)
    right_arm_pos = _read_arm_joint_positions(args.right_port)
    if args.arm_only:
        print("Hand reads disabled. Writing zero hand joints as placeholders.")
        left_hand_pos = ZERO_HAND_POS.copy()
        right_hand_pos = ZERO_HAND_POS.copy()
    else:
        left_hand_pos = _read_hand_joint_positions(
            "left",
            channel_mode=args.channel_mode,
            device_id=args.device_id,
            canfd_id=args.canfd_id,
            channel_id=args.left_channel_id,
        )
        right_hand_pos = _read_hand_joint_positions(
            "right",
            channel_mode=args.channel_mode,
            device_id=args.device_id,
            canfd_id=args.canfd_id,
            channel_id=args.right_channel_id,
        )

    _print_joint_summary("left", left_arm_pos, left_hand_pos)
    _print_joint_summary("right", right_arm_pos, right_hand_pos)

    _save_reset_file(args.left_output, _build_reset_payload(left_arm_pos, left_hand_pos))
    _save_reset_file(args.right_output, _build_reset_payload(right_arm_pos, right_hand_pos))

    print(f"\nSaved left reset pose to {Path(args.left_output).expanduser()}")
    print(f"Saved right reset pose to {Path(args.right_output).expanduser()}")


if __name__ == "__main__":
    main()
