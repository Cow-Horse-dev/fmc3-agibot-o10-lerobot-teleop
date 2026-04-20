#!/usr/bin/env python3
"""Set arm and hand joint positions to inspect poses.

Usage:
    # Move to reset pose from JSON file:
    python scripts/set_pose.py --from-json configs/o10_right_reset_pose.json

    # Set arm joints directly (6 values, radians):
    python scripts/set_pose.py --arm 0.0 0.0 0.0 0.0 0.0 0.0

    # Set hand joints directly (10 values, radians):
    python scripts/set_pose.py --hand 0.0 -1.14 0.37 0.0 0.22 0.09 0.02 0.04 0.02 0.07

    # Set both:
    python scripts/set_pose.py --arm 0 0 0 0 0 0 --hand 0 -1.14 0.37 0 0.22 0.09 0.02 0.04 0.02 0.07

    # Only read current pose (no movement):
    python scripts/set_pose.py --read-only

    # Use CAN port (default: can0):
    python scripts/set_pose.py --port can1 --arm 0 0 0 0 0 0
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


def load_pose_from_json(path: str) -> tuple[list[float] | None, list[float] | None]:
    with open(path) as f:
        data = json.load(f)
    groups = data.get("groups", {})
    arm_vals = None
    hand_vals = None
    if "arm" in groups:
        jv = groups["arm"]["joint_values"]
        arm_vals = [jv[name] for name in AGIBOT_O10_ARM_FEATURE_NAMES]
    if "hand" in groups:
        jv = groups["hand"]["joint_values"]
        hand_vals = [jv[name] for name in AGIBOT_O10_HAND_FEATURE_NAMES]
    return arm_vals, hand_vals


def print_pose(label: str, names: tuple[str, ...], values: list[float]):
    print(f"\n{label}:")
    for name, val in zip(names, values):
        print(f"  {name:>25s}: {val:+.6f}")


def move_arm_to(arm, target: list[float], vel: float = 0.8, eff: float = 10.0, tol: float = 0.02):
    n = len(target)
    velocities = [vel] * n
    effort = [eff] * n
    print(f"\nMoving arm to target (tolerance={tol})...")
    for step in range(5000):
        state = list(arm.state().pos)[:n]
        if all(abs(t - s) <= tol for t, s in zip(target, state)):
            print(f"  Arm arrived after {step} steps.")
            return
        arm.pvt(target, velocities, effort)
        time.sleep(0.004)
    print("  Warning: arm did not converge within 5000 steps.")


def main():
    parser = argparse.ArgumentParser(description="Set arm/hand pose for inspection")
    parser.add_argument("--from-json", type=str, help="Load pose from reset_pose JSON file")
    parser.add_argument("--arm", type=float, nargs=ARM_DOF, help=f"Arm joint positions ({ARM_DOF} floats, radians)")
    parser.add_argument("--hand", type=float, nargs=HAND_DOF, help=f"Hand joint positions ({HAND_DOF} floats, radians)")
    parser.add_argument("--read-only", action="store_true", help="Only read and print current pose")
    parser.add_argument("--port", type=str, default="can0", help="CAN port (default: can0)")
    parser.add_argument("--handedness", type=str, default="right", choices=["left", "right"])
    args = parser.parse_args()

    arm_target = None
    hand_target = None

    if args.from_json:
        arm_target, hand_target = load_pose_from_json(args.from_json)
        print(f"Loaded pose from {args.from_json}")
    if args.arm is not None:
        arm_target = args.arm
    if args.hand is not None:
        hand_target = args.hand

    if not args.read_only and arm_target is None and hand_target is None:
        parser.error("Provide --from-json, --arm, --hand, or --read-only")

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

    arm.enable()
    arm.set_param("arm.control_mode", ah.MotorControlMode.PVT)

    cur_arm = list(arm.state().pos)[:ARM_DOF]
    cur_hand = hand.read_active_joint_angles()
    print_pose("Current arm", AGIBOT_O10_ARM_FEATURE_NAMES, cur_arm)
    print_pose("Current hand", AGIBOT_O10_HAND_FEATURE_NAMES, cur_hand)

    if args.read_only:
        print("\n(read-only mode, no movement)")
    else:
        if arm_target is not None:
            print_pose("Target arm", AGIBOT_O10_ARM_FEATURE_NAMES, arm_target)
            move_arm_to(arm, arm_target)
        if hand_target is not None:
            print_pose("Target hand", AGIBOT_O10_HAND_FEATURE_NAMES, hand_target)
            print("Setting hand joints...")
            hand.write_active_joint_angles(hand_target)
            time.sleep(0.5)

        final_arm = list(arm.state().pos)[:ARM_DOF]
        final_hand = hand.read_active_joint_angles()
        print_pose("Final arm", AGIBOT_O10_ARM_FEATURE_NAMES, final_arm)
        print_pose("Final hand", AGIBOT_O10_HAND_FEATURE_NAMES, final_hand)

    input("\nPress Enter to disable motors and exit...")
    arm.disable()
    arm.uninit()
    hand.disconnect()
    print("Done.")


if __name__ == "__main__":
    main()
