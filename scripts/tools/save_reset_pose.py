#!/usr/bin/env python3
"""Read current arm+hand joint angles and print them for reference.

NOTE: The YAML configs now use reset_poses_path + reset_gesture to point at the
centralized JSON under configs/reset_poses/ (e.g. o10_dual_reset.json).
This script is a diagnostic helper — it reads live joint angles and prints them
so you can manually update the centralized JSON if needed.

Usage:
    python scripts/tools/save_reset_pose.py
    python scripts/tools/save_reset_pose.py --port can0 --handedness right
"""

import argparse
import json
import sys
import time

import airbot_hardware_py as ah

sys.path.insert(0, "qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any")
from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AgibotO10Hand,
)

ARM_DOF = len(AGIBOT_O10_ARM_FEATURE_NAMES)
HAND_DOF = len(AGIBOT_O10_HAND_FEATURE_NAMES)


def main():
    parser = argparse.ArgumentParser(description="Save current joint angles as reset pose")
    parser.add_argument("--output", type=str, default="configs/o10_right_reset_pose.json")
    parser.add_argument("--port", type=str, default="can0")
    parser.add_argument("--handedness", type=str, default="right", choices=["left", "right"])
    args = parser.parse_args()

    executor = ah.create_asio_executor(8)
    io_context = executor.get_io_context()
    arm = ah.Play.create(
        ah.MotorType.OD, ah.MotorType.OD, ah.MotorType.OD,
        ah.MotorType.DM, ah.MotorType.DM, ah.MotorType.DM,
        ah.EEFType.NA, ah.MotorType.NA,
    )

    print(f"Connecting arm on {args.port}...")
    if not arm.init(io_context, args.port, 250):
        print("ERROR: Failed to initialize arm")
        sys.exit(1)

    hand = AgibotO10Hand(handedness=args.handedness, channel_mode="multiChannel")
    print(f"Connecting {args.handedness} hand...")
    hand.connect()

    time.sleep(0.1)
    arm_pos = list(arm.state().pos)[:ARM_DOF]
    hand_pos = hand.read_active_joint_angles()

    print("\nCurrent arm joints:")
    for name, val in zip(AGIBOT_O10_ARM_FEATURE_NAMES, arm_pos):
        print(f"  {name:>25s}: {val:+.6f}")
    print("\nCurrent hand joints:")
    for name, val in zip(AGIBOT_O10_HAND_FEATURE_NAMES, hand_pos):
        print(f"  {name:>25s}: {val:+.6f}")

    payload = {
        "groups": {
            "arm": {
                "feature_names": list(AGIBOT_O10_ARM_FEATURE_NAMES),
                "joint_values": {
                    name: val for name, val in zip(AGIBOT_O10_ARM_FEATURE_NAMES, arm_pos)
                },
            },
            "hand": {
                "feature_names": list(AGIBOT_O10_HAND_FEATURE_NAMES),
                "joint_values": {
                    name: val for name, val in zip(AGIBOT_O10_HAND_FEATURE_NAMES, hand_pos)
                },
            },
        }
    }

    with open(args.output, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)
        f.write("\n")

    print(f"\nSaved to {args.output}")

    arm.uninit()
    hand.disconnect()


if __name__ == "__main__":
    main()
